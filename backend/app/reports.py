from __future__ import annotations

from io import BytesIO
from statistics import mean

from reportlab.graphics.charts.barcharts import HorizontalBarChart, VerticalBarChart
from reportlab.graphics.charts.piecharts import Pie
from reportlab.graphics.shapes import Circle, Drawing, Line, Rect, String
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from .models import (
    LatencyMetric,
    MachineCommand,
    MonitoringSession,
    QualityReport,
    SafetyEvent,
)
from .store import JsonStore


def percentile(values: list[float], percentile_value: float) -> float:
    if not values:
        return 0
    ordered = sorted(values)
    index = min(len(ordered) - 1, round((len(ordered) - 1) * percentile_value))
    return round(ordered[index], 2)


def chart_label(value: float) -> str:
    return f"{value:.1f}" if value % 1 else str(int(value))


class ReportService:
    def __init__(self, store: JsonStore):
        self.store = store

    def generate(self, session: MonitoringSession) -> QualityReport:
        events = [item for item in self.store.list("events", SafetyEvent) if item.session_id == session.id]
        commands = [
            item for item in self.store.list("machine_commands", MachineCommand) if item.session_id == session.id
        ]
        infractions = [item for item in self.store.data["infractions"] if item["session_id"] == session.id]
        total_samples = sum(track.samples for track in session.tracks.values())
        compliant = sum(track.compliant_samples for track in session.tracks.values())
        latencies = [item.server_total_ms for item in session.latency_metrics]
        end = session.ended_at or session.started_at
        existing = next((item for item in self.store.list("reports", QualityReport) if item.session_id == session.id), None)
        report_data = {"id": existing.id} if existing else {}
        report = QualityReport(
            **report_data,
            session_id=session.id,
            duration_seconds=max(0, (end - session.started_at).total_seconds()),
            required_ppe=session.required_ppe,
            compliance_percent=round((compliant / total_samples * 100) if total_samples else 0, 2),
            events_by_severity={
                str(level): sum(1 for event in events if event.severity == level) for level in (1, 2, 3)
            },
            infractions=len(infractions),
            machine_cuts=sum(1 for command in commands if command.action == "CUT"),
            latency={
                "average_ms": round(mean(latencies), 2) if latencies else 0,
                "p50_ms": percentile(latencies, 0.5),
                "p95_ms": percentile(latencies, 0.95),
            },
            track_summaries=list(session.tracks.values()),
            events=sorted(events, key=lambda event: event.started_at),
            timeline=sorted(session.timeline, key=lambda item: item.timestamp),
            posture_timeline=sorted(session.posture_timeline, key=lambda item: item.timestamp),
            session_started_at=session.started_at,
            session_ended_at=session.ended_at,
        )
        self.store.upsert("reports", report, id_field="session_id")
        return report

    def pdf(self, report: QualityReport) -> bytes:
        buffer = BytesIO()
        styles = getSampleStyleSheet()
        doc = SimpleDocTemplate(buffer, pagesize=A4, title=f"Relatório {report.session_id}")
        story = [
            Paragraph("Relatório de Qualidade — EPI Guard", styles["Title"]),
            Paragraph(f"Sessão: {report.session_id}", styles["Normal"]),
            Paragraph(f"Gerado em: {report.generated_at.strftime('%d/%m/%Y %H:%M:%S UTC')}", styles["Normal"]),
            Spacer(1, 16),
        ]
        overview = [
            ["Duração", f"{report.duration_seconds:.1f} s"],
            ["Conformidade", f"{report.compliance_percent:.1f}%"],
            ["Infrações", str(report.infractions)],
            ["Cortes simulados", str(report.machine_cuts)],
            ["Latência média", f"{report.latency['average_ms']:.1f} ms"],
            ["Latência p95", f"{report.latency['p95_ms']:.1f} ms"],
        ]
        table = Table(overview, colWidths=[170, 250])
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#E7EEF9")),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#B7C5D8")),
                    ("PADDING", (0, 0), (-1, -1), 8),
                ]
            )
        )
        story.extend([table, Spacer(1, 18), Paragraph("Indicadores visuais", styles["Heading2"])])
        story.extend([
            self._compliance_pie(report),
            Spacer(1, 12),
            self._severity_chart(report),
            Spacer(1, 12),
            self._track_chart(report),
            Spacer(1, 12),
            self._posture_summary_chart(report),
            Spacer(1, 12),
            self._posture_pose_gallery(report),
            Spacer(1, 12),
            self._timeline_chart(report),
            Spacer(1, 18),
            Paragraph("Pessoas monitoradas", styles["Heading2"]),
        ])
        rows = [["Track", "Amostras", "Conformes", "Percentual"]]
        for track in report.track_summaries:
            percent = track.compliant_samples / track.samples * 100 if track.samples else 0
            rows.append([track.track_id, str(track.samples), str(track.compliant_samples), f"{percent:.1f}%"])
        track_table = Table(rows, repeatRows=1, colWidths=[120, 100, 100, 100])
        track_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#14324A")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#B7C5D8")),
                    ("PADDING", (0, 0), (-1, -1), 7),
                ]
            )
        )
        story.append(track_table)
        doc.build(story)
        return buffer.getvalue()


    def _posture_summary_chart(self, report: QualityReport) -> Drawing:
        samples = report.posture_timeline
        drawing = Drawing(460, 165)
        drawing.add(String(0, 148, "Postura ergonomica", fontSize=11, fillColor=colors.HexColor("#14324A")))
        drawing.add(String(0, 132, "Media de REBA e score ergonomico por pessoa/track", fontSize=8, fillColor=colors.HexColor("#475569")))
        if not samples:
            drawing.add(String(0, 92, "Sem amostras de postura registradas nesta sessao.", fontSize=9, fillColor=colors.HexColor("#64748B")))
            return drawing

        track_ids = []
        for item in samples:
            if item.track_id not in track_ids:
                track_ids.append(item.track_id)
        y = 104
        for track_id in track_ids[:5]:
            items = [item for item in samples if item.track_id == track_id]
            avg_reba = sum(item.reba_score for item in items) / len(items)
            avg_score = sum(item.ergonomic_score for item in items) / len(items)
            worst = max(item.severity for item in items)
            label = "Inapto" if worst >= 2 else "Atencao" if worst == 1 else "Apto"
            color = colors.HexColor("#EF4444") if worst >= 2 else colors.HexColor("#F59E0B") if worst == 1 else colors.HexColor("#22C55E")
            drawing.add(String(0, y, track_id, fontSize=8, fillColor=colors.HexColor("#0F172A")))
            drawing.add(String(72, y, label, fontSize=8, fillColor=color))
            drawing.add(String(145, y, f"REBA medio: {avg_reba:.1f}", fontSize=8, fillColor=colors.HexColor("#475569")))
            drawing.add(String(260, y, f"Score: {avg_score:.1f}/100", fontSize=8, fillColor=colors.HexColor("#475569")))
            drawing.add(Rect(360, y - 1, max(2, min(90, avg_score * 0.9)), 6, fillColor=color, strokeColor=None))
            y -= 22
        return drawing

    def _posture_pose_gallery(self, report: QualityReport) -> Drawing:
        drawing = Drawing(460, 250)
        drawing.add(String(0, 232, "Amostras visuais de postura 3D", fontSize=11, fillColor=colors.HexColor("#14324A")))
        drawing.add(String(0, 216, "Esqueletos gerados em memoria a partir dos keypoints; nenhuma foto da camera e salva.", fontSize=8, fillColor=colors.HexColor("#475569")))
        samples = [item for item in report.posture_timeline if item.keypoints_3d]
        if not samples:
            drawing.add(String(0, 145, "Sem keypoints suficientes para renderizar amostras de postura.", fontSize=9, fillColor=colors.HexColor("#64748B")))
            return drawing

        selected = []
        for track_id in []:
            pass
        track_ids = []
        for item in samples:
            if item.track_id not in track_ids:
                track_ids.append(item.track_id)
        for track_id in track_ids:
            track_samples = [item for item in samples if item.track_id == track_id]
            worst = max(track_samples, key=lambda item: (item.severity, item.reba_score, -item.ergonomic_score))
            latest = track_samples[-1]
            selected.append(worst)
            if latest is not worst:
                selected.append(latest)
        selected = selected[:4]

        skeleton = ((1, 0), (2, 1), (3, 2), (4, 0), (5, 4), (6, 5), (7, 0), (17, 7), (9, 8), (10, 9), (11, 8), (12, 11), (13, 12), (14, 8), (15, 14), (16, 15), (17, 8))

        def draw_pose(item, x0: float, y0: float, w: float, h: float) -> None:
            pts = item.keypoints_3d[:18]
            xs = [point[0] for point in pts]
            ys = [-point[1] for point in pts]
            min_x, max_x = min(xs), max(xs)
            min_y, max_y = min(ys), max(ys)
            span_x = max(1e-6, max_x - min_x)
            span_y = max(1e-6, max_y - min_y)
            scale = min((w - 18) / span_x, (h - 42) / span_y)
            cx = x0 + w / 2
            cy = y0 + 52

            def project(index: int) -> tuple[float, float]:
                px = cx + (pts[index][0] - (min_x + max_x) / 2) * scale
                py = cy + ((-pts[index][1]) - (min_y + max_y) / 2) * scale
                return px, py

            severity = item.severity
            line_color = colors.HexColor("#EF4444") if severity >= 2 else colors.HexColor("#F59E0B") if severity == 1 else colors.HexColor("#22C55E")
            drawing.add(Rect(x0, y0, w, h, fillColor=colors.HexColor("#F8FAFC"), strokeColor=colors.HexColor("#CBD5E1")))
            drawing.add(String(x0 + 8, y0 + h - 14, f"{item.track_id} | REBA {item.reba_score:.0f} | {item.ergonomic_score:.0f}/100", fontSize=7, fillColor=colors.HexColor("#0F172A")))
            drawing.add(String(x0 + 8, y0 + 8, item.state.upper(), fontSize=7, fillColor=line_color))
            for a, b in skeleton:
                if a < len(pts) and b < len(pts):
                    ax, ay = project(a)
                    bx, by = project(b)
                    drawing.add(Line(ax, ay, bx, by, strokeColor=line_color, strokeWidth=1.3))
            for index in range(min(18, len(pts))):
                px, py = project(index)
                drawing.add(Circle(px, py, 1.6, fillColor=colors.HexColor("#0F172A"), strokeColor=None))

        positions = [(0, 104), (235, 104), (0, 0), (235, 0)]
        for item, (x, y) in zip(selected, positions):
            draw_pose(item, x, y, 215, 95)
        return drawing

    def _timeline_chart(self, report: QualityReport) -> Drawing:
        rows = []
        keys = []
        for track in report.track_summaries:
            for code in report.required_ppe:
                key = (track.track_id, code)
                if key not in keys:
                    keys.append(key)
        for item in report.timeline:
            key = (item.track_id, item.ppe_code)
            if key not in keys:
                keys.append(key)
        for event in report.events:
            key = (event.track_id, event.ppe_code)
            if key not in keys:
                keys.append(key)
        rows = keys[:8]
        row_height = 18
        drawing_height = max(135, 78 + len(rows) * row_height)
        drawing = Drawing(460, drawing_height)
        drawing.add(String(0, drawing_height - 16, "Evolu\u00e7\u00e3o temporal da sess\u00e3o", fontSize=11, fillColor=colors.HexColor("#14324A")))
        drawing.add(String(0, drawing_height - 32, "Verde: conforme | Cinza: ausente sem alerta | Amarelo/Rosa/Vermelho: níveis 1/2/3", fontSize=8, fillColor=colors.HexColor("#475569")))

        start = report.session_started_at or report.generated_at
        end = report.session_ended_at or start
        duration = max(1, (end - start).total_seconds() or report.duration_seconds or 1)
        x0, y0, width = 88, drawing_height - 62, 330
        tick_color = colors.HexColor("#CBD5E1")
        for ratio in (0, 0.25, 0.5, 0.75, 1):
            x = x0 + width * ratio
            drawing.add(Rect(x, y0 - max(8, len(rows) * row_height), 0.5, max(8, len(rows) * row_height), fillColor=tick_color, strokeColor=tick_color))
            drawing.add(String(x - 8, y0 + 8, f"{int(duration * ratio)}s", fontSize=7, fillColor=colors.HexColor("#64748B")))

        def status_color(state: str, severity: int):
            if severity >= 3:
                return colors.HexColor("#EF4444")
            if severity == 2:
                return colors.HexColor("#FB7185")
            if severity == 1:
                return colors.HexColor("#F59E0B")
            if state != "present":
                return colors.HexColor("#94A3B8")
            return colors.HexColor("#22C55E")

        def draw_segment(row_y: float, left_s: float, right_s: float, state: str, severity: int):
            left = max(0, min(duration, left_s))
            right = max(left + 0.3, min(duration, right_s))
            x = x0 + width * (left / duration)
            w = max(1.5, width * ((right - left) / duration))
            drawing.add(Rect(x, row_y, w, 9, fillColor=status_color(state, severity), strokeColor=None))

        for index, (track_id, ppe_code) in enumerate(rows):
            row_y = y0 - 18 - index * row_height
            drawing.add(String(0, row_y + 1, f"{track_id} / {ppe_code}", fontSize=7, fillColor=colors.HexColor("#0F172A")))
            drawing.add(Rect(x0, row_y, width, 9, fillColor=colors.HexColor("#E2E8F0"), strokeColor=None))
            samples = [item for item in report.timeline if item.track_id == track_id and item.ppe_code == ppe_code]
            samples.sort(key=lambda item: item.timestamp)
            if samples:
                current = samples[0]
                segment_start = max(0, (current.timestamp - start).total_seconds())
                for sample in samples[1:]:
                    changed = sample.state != current.state or sample.severity != current.severity
                    if changed:
                        segment_end = max(segment_start + 0.3, (sample.timestamp - start).total_seconds())
                        draw_segment(row_y, segment_start, segment_end, current.state.value if hasattr(current.state, "value") else str(current.state), current.severity)
                        current = sample
                        segment_start = (sample.timestamp - start).total_seconds()
                draw_segment(row_y, segment_start, duration, current.state.value if hasattr(current.state, "value") else str(current.state), current.severity)
            else:
                track = next((item for item in report.track_summaries if item.track_id == track_id), None)
                percent = track.compliant_samples / track.samples * 100 if track and track.samples else 100
                draw_segment(row_y, 0, duration, "present" if percent >= 99.5 else "unknown", 0 if percent >= 99.5 else -1)
        if len(keys) > len(rows):
            drawing.add(String(0, 10, f"+ {len(keys) - len(rows)} linhas omitidas para manter o PDF compacto", fontSize=8, fillColor=colors.HexColor("#64748B")))
        return drawing


    def _compliance_pie(self, report: QualityReport) -> Drawing:
        drawing = Drawing(460, 150)
        drawing.add(String(0, 132, "Conformidade geral da sessão", fontSize=11, fillColor=colors.HexColor("#14324A")))
        compliant = max(0, min(100, report.compliance_percent))
        pie = Pie()
        pie.x = 8
        pie.y = 18
        pie.width = 110
        pie.height = 110
        pie.data = [compliant, max(0, 100 - compliant)]
        pie.labels = [f"Conforme {compliant:.1f}%", f"Não conforme {100 - compliant:.1f}%"]
        pie.slices[0].fillColor = colors.HexColor("#22C55E")
        pie.slices[1].fillColor = colors.HexColor("#EF4444")
        drawing.add(pie)
        drawing.add(String(160, 86, f"Aderência: {compliant:.1f}%", fontSize=18, fillColor=colors.HexColor("#0F172A")))
        drawing.add(String(160, 62, f"Duração analisada: {report.duration_seconds:.1f} s", fontSize=10, fillColor=colors.HexColor("#475569")))
        drawing.add(String(160, 44, f"EPIs exigidos: {', '.join(report.required_ppe)}", fontSize=10, fillColor=colors.HexColor("#475569")))
        return drawing

    def _severity_chart(self, report: QualityReport) -> Drawing:
        drawing = Drawing(460, 180)
        drawing.add(String(0, 162, "Eventos por severidade", fontSize=11, fillColor=colors.HexColor("#14324A")))
        values = [report.events_by_severity.get(str(level), 0) for level in (1, 2, 3)]
        chart = VerticalBarChart()
        chart.x = 38
        chart.y = 28
        chart.height = 110
        chart.width = 360
        chart.data = [values]
        chart.categoryAxis.categoryNames = ["Nível 1", "Nível 2", "Nível 3"]
        chart.valueAxis.valueMin = 0
        chart.valueAxis.valueMax = max(3, max(values) + 1)
        chart.valueAxis.valueStep = 1
        chart.bars[0].fillColor = colors.HexColor("#F59E0B")
        drawing.add(chart)
        return drawing

    def _track_chart(self, report: QualityReport) -> Drawing:
        drawing = Drawing(460, 190)
        drawing.add(String(0, 172, "Conformidade por pessoa/track", fontSize=11, fillColor=colors.HexColor("#14324A")))
        labels = [track.track_id for track in report.track_summaries[:6]] or ["Sem tracks"]
        values = [
            round(track.compliant_samples / track.samples * 100, 1) if track.samples else 0
            for track in report.track_summaries[:6]
        ] or [0]
        chart = HorizontalBarChart()
        chart.x = 86
        chart.y = 28
        chart.height = 120
        chart.width = 310
        chart.data = [values]
        chart.categoryAxis.categoryNames = labels
        chart.valueAxis.valueMin = 0
        chart.valueAxis.valueMax = 100
        chart.valueAxis.valueStep = 20
        chart.bars[0].fillColor = colors.HexColor("#38BDF8")
        drawing.add(chart)
        return drawing

