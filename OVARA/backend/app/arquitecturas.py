"""Arquitecturas de red del modelo OVARA (idénticas a las del experimento; sin descargar pesos)."""
from __future__ import annotations

import torch
import torch.nn as nn
import torch.nn.functional as F
from torchvision import models


def crear_clasificador(arch: str) -> nn.Module:
    """CNN binaria (endometrioma sí/no) sobre el recorte de la lesión."""
    if arch == "resnet18":
        m = models.resnet18(weights=None)
        m.fc = nn.Linear(m.fc.in_features, 1)
    elif arch == "efficientnet_b0":
        m = models.efficientnet_b0(weights=None)
        m.classifier[1] = nn.Linear(m.classifier[1].in_features, 1)
    elif arch == "convnext_tiny":
        m = models.convnext_tiny(weights=None)
        m.classifier[2] = nn.Linear(m.classifier[2].in_features, 1)
    else:
        raise ValueError(f"Arquitectura no soportada: {arch}")
    return m


def capa_gradcam(m: nn.Module, arch: str) -> nn.Module:
    return m.layer4 if arch == "resnet18" else m.features[-1]


class _Sube(nn.Module):
    def __init__(self, c_in, c_skip, c_out):
        super().__init__()
        self.conv = nn.Sequential(nn.Conv2d(c_in + c_skip, c_out, 3, padding=1, bias=False), nn.BatchNorm2d(c_out), nn.ReLU(inplace=True),
                                  nn.Conv2d(c_out, c_out, 3, padding=1, bias=False), nn.BatchNorm2d(c_out), nn.ReLU(inplace=True))

    def forward(self, x, skip):
        x = F.interpolate(x, size=skip.shape[-2:], mode="bilinear", align_corners=False)
        return self.conv(torch.cat([x, skip], 1))


class UNetResNet18(nn.Module):
    """U-Net con codificador ResNet18: localiza la lesión (logit por píxel)."""
    def __init__(self):
        super().__init__()
        r = models.resnet18(weights=None)
        self.inicio, self.pool = nn.Sequential(r.conv1, r.bn1, r.relu), r.maxpool
        self.c1, self.c2, self.c3, self.c4 = r.layer1, r.layer2, r.layer3, r.layer4
        self.s4, self.s3, self.s2, self.s1 = _Sube(512, 256, 256), _Sube(256, 128, 128), _Sube(128, 64, 64), _Sube(64, 64, 64)
        self.final = nn.Sequential(nn.Conv2d(64, 32, 3, padding=1), nn.ReLU(inplace=True), nn.Conv2d(32, 1, 1))

    def forward(self, x):
        x0 = self.inicio(x)
        x1 = self.c1(self.pool(x0))
        x2 = self.c2(x1); x3 = self.c3(x2); x4 = self.c4(x3)
        d = self.s1(self.s2(self.s3(self.s4(x4, x3), x2), x1), x0)
        return F.interpolate(self.final(d), size=x.shape[-2:], mode="bilinear", align_corners=False)
