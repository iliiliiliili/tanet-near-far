import torch.nn as nn
from torch.nn.modules.activation import ReLU
from torch.nn.modules.batchnorm import BatchNorm2d


class Involution(nn.Module):

    def __init__(
        self,
        channels,
        kernel_size,
        stride=1,
        bias=True,
        padding=0,
        **kwargs,
    ):
        super(Involution, self).__init__()
        self.kernel_size = kernel_size
        self.stride = stride
        self.channels = channels
        reduction_ratio = 4
        self.group_channels = 16
        self.groups = self.channels // self.group_channels
        self.conv1 = nn.Sequential(
            nn.Conv2d(
                in_channels=channels,
                out_channels=channels // reduction_ratio,
                kernel_size=1,
                bias=False,
                **kwargs,
            ),
            BatchNorm2d(channels // reduction_ratio),
            ReLU(True),
        )
        self.conv2 = nn.Conv2d(
            in_channels=channels // reduction_ratio,
            out_channels=kernel_size**2 * self.groups,
            kernel_size=1,
            stride=1,
            bias=bias,
            **kwargs,
        )
        if stride > 1:
            self.avgpool = nn.AvgPool2d(stride, stride)
        self.unfold = nn.Unfold(kernel_size, 1, (kernel_size-1)//2, stride)

    def forward(self, x):
        weight = self.conv2(self.conv1(
            x if self.stride == 1 else self.avgpool(x)))
        b, c, h, w = weight.shape
        weight = weight.view(
            b, self.groups, self.kernel_size**2, h, w).unsqueeze(2)
        out = self.unfold(x).view(
            b, self.groups, self.group_channels, self.kernel_size**2, h, w)
        out = (weight * out).sum(dim=3).view(b, self.channels, h, w)
        return out
