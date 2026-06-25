import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.nn import init


class h_sigmoid(nn.Module):
    def __init__(self):
        super(h_sigmoid, self).__init__()

    def forward(self, x):
        return F.relu6(x + 3.) / 6.


class h_swish(nn.Module):
    def __init__(self, inplace=True):
        super(h_swish, self).__init__()
        self.sigmoid = h_sigmoid()

    def forward(self, x):
        return x * self.sigmoid(x)


class SEModule(nn.Module):
    def __init__(self, channel, reduction=4):
        super(SEModule, self).__init__()
        self.avg_pool = nn.AdaptiveAvgPool2d(1)  # batchsize * channel * 1 * 1
        self.fc = nn.Sequential(
            nn.Linear(channel, channel // reduction, bias=False),
            nn.ReLU(inplace=True),
            nn.Linear(channel // reduction, channel, bias=False),
            h_sigmoid()
            # nn.Sigmoid()
        )

    def forward(self, x):
        b, c, _, _ = x.size()
        y = self.avg_pool(x).view(b, c) # batchsize * channel
        y = self.fc(y).view(b, c, 1, 1) # batchsize * channel * 1 * 1
        return x * y.expand_as(x)       # batchsize * channel * H * W


class Identity(nn.Module):
    def __init__(self, channel):
        super(Identity, self).__init__()

    def forward(self, x):
        return x

class MobileBottleneck(nn.Module):
    def __init__(self, inp, oup, kernel, stride, exp, se=False, nl='RE'):
        super(MobileBottleneck, self).__init__()
        assert stride in [1, 2]
        assert kernel in [3, 5]
        padding = (kernel - 1) // 2
        self.use_res_connect = stride == 1
        conv_layer = nn.Conv2d
        norm_layer = nn.BatchNorm2d
        if nl == 'RE':
            nlin_layer = nn.ReLU6 # or ReLU6
        elif nl == 'HS':
            nlin_layer = h_swish
        else:
            raise NotImplementedError
        if se:
            SELayer = SEModule
        else:
            SELayer = Identity

        self.conv = nn.Sequential(
            # pw
            conv_layer(inp, exp*oup, 1, 1, 0, bias=False),
            norm_layer(exp*oup),
            nlin_layer(inplace=True),
            # dw
            conv_layer(exp*oup, exp*oup, kernel, stride, padding, groups=exp*oup, bias=False),
            norm_layer(exp*oup),
            SELayer(exp*oup),
            nlin_layer(inplace=True),
            # pw-linear
            conv_layer(exp*oup, oup, 1, 1, 0, bias=False),
            norm_layer(oup),
        )
        self.shortcut = nn.Sequential()
        if stride == 1 and inp != oup:
            self.shortcut = nn.Sequential(
                nn.Conv2d(inp, oup, kernel_size=1, stride=1, padding=0, bias=False),
                nn.BatchNorm2d(oup),
            )

    def forward(self, x):
        if self.use_res_connect:
            return self.shortcut(x) + self.conv(x)
        else:
            return self.conv(x)


class MobileNetv2(nn.Module):
    """MobileNet2 implementation.
    """

    def __init__(self, num_joints=18, expansion_factor = 6):
        super(MobileNetv2, self).__init__()
        
        self.num_joints = num_joints
        self.expansion_factor = expansion_factor

        self.conv1 = nn.Conv2d(3, 32, kernel_size=3, stride=2, padding=1, bias=False)
        self.bn1 = nn.BatchNorm2d(32)
        self.nlin1 = nn.ReLU6(inplace=True)

        self.bneck = nn.Sequential(
            MobileBottleneck(inp = 32, oup = 16, kernel = 3, stride = 1, exp = 1),

            MobileBottleneck(inp = 16, oup = 24, kernel = 3, stride = 2, exp = self.expansion_factor),
            MobileBottleneck(inp = 24, oup = 24, kernel = 3, stride = 1, exp = self.expansion_factor),

            MobileBottleneck(inp = 24, oup = 32, kernel = 3, stride = 2, exp = self.expansion_factor),
            MobileBottleneck(inp = 32, oup = 32, kernel = 3, stride = 1, exp = self.expansion_factor),
            MobileBottleneck(inp = 32, oup = 32, kernel = 3, stride = 1, exp = self.expansion_factor),

            MobileBottleneck(inp = 32, oup = 64, kernel = 3, stride = 2, exp = self.expansion_factor),
            MobileBottleneck(inp = 64, oup = 64, kernel = 3, stride = 1, exp = self.expansion_factor),
            MobileBottleneck(inp = 64, oup = 64, kernel = 3, stride = 1, exp = self.expansion_factor),
            MobileBottleneck(inp = 64, oup = 64, kernel = 3, stride = 1, exp = self.expansion_factor),

            MobileBottleneck(inp = 64, oup = 96, kernel = 3, stride = 1, exp = self.expansion_factor),
            MobileBottleneck(inp = 96, oup = 96, kernel = 3, stride = 1, exp = self.expansion_factor),
            MobileBottleneck(inp = 96, oup = 96, kernel = 3, stride = 1, exp = self.expansion_factor),

            MobileBottleneck(inp = 96, oup = 160, kernel = 3, stride = 2, exp = self.expansion_factor),
            MobileBottleneck(inp = 160, oup = 160, kernel = 3, stride = 1, exp = self.expansion_factor),
            MobileBottleneck(inp = 160, oup = 160, kernel = 3, stride = 1, exp = self.expansion_factor),

            MobileBottleneck(inp = 160, oup = 320, kernel = 3, stride = 1, exp = self.expansion_factor),
        )

        self.conv2 = nn.Conv2d(320, 1280, kernel_size=1, stride=1, padding=0, bias=False)
        self.bn2 = nn.BatchNorm2d(1280)
        self.nlin2 = nn.ReLU6(inplace=True)

        self.init_params()

    def init_params(self):
        for m in self.modules():
            if isinstance(m, nn.Conv2d):
                init.kaiming_normal_(m.weight, mode='fan_out')
                if m.bias is not None:
                    init.constant_(m.bias, 0)
            elif isinstance(m, nn.BatchNorm2d):
                init.constant_(m.weight, 1)
                init.constant_(m.bias, 0)
            elif isinstance(m, nn.Linear):
                init.normal_(m.weight, std=0.001)
                if m.bias is not None:
                    init.constant_(m.bias, 0)

    def forward(self, x):
        x = self.conv1(x)
        x = self.bn1(x)
        x = self.nlin1(x)

        x = self.bneck(x)

        x = self.conv2(x)
        x = self.bn2(x)
        x = self.nlin2(x) # batch_size * 1280 * H/32 * W/32

        return x


