from __future__ import annotations

from io import BytesIO
from statistics import mean

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
        report = QualityReport(
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
        )
        self.store.upsert("reports", report)
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
        story.extend([table, Spacer(1, 18), Paragraph("Pessoas monitoradas", styles["Heading2"])])
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

