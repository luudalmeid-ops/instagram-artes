"""Desenha o ícone do app (zumbi em pixel art 32x32) e exporta em 192 e 512 px."""
import os
from PIL import Image

N = 32
img = Image.new("RGBA", (N, N))
px = img.load()

def rect(x, y, w, h, c):
    for j in range(y, y + h):
        for i in range(x, x + w):
            if 0 <= i < N and 0 <= j < N:
                px[i, j] = c

def hexc(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4)) + (255,)

# Fundo vermelho com vinheta em degraus
fundo = [hexc(c) for c in ("#d63a2a", "#a8201b", "#741212", "#420909")]
for y in range(N):
    for x in range(N):
        d = ((x - 15.5) ** 2 + (y - 13) ** 2) ** .5
        px[x, y] = fundo[min(3, int(d / 6.5))]

# Camisa rasgada
rect(4, 27, 24, 5, hexc("#2e3b4e")); rect(4, 27, 24, 1, hexc("#45556b"))
rect(7, 29, 2, 2, hexc("#8e1010")); rect(22, 28, 3, 2, hexc("#8e1010")); rect(14, 30, 1, 2, hexc("#420909"))
# Pescoço
rect(12, 24, 8, 4, hexc("#4f7a3a"))

PELE, SOMBRA, LUZ = hexc("#83b35c"), hexc("#55803d"), hexc("#a9d17f")
cabeca = set()
def pele(x, y, w, h):
    rect(x, y, w, h, PELE)
    cabeca.update((i, j) for i in range(x, x + w) for j in range(y, y + h))
pele(9, 4, 14, 1); pele(8, 5, 16, 1); pele(7, 6, 18, 15); pele(8, 21, 16, 2); pele(9, 23, 14, 1); pele(11, 24, 10, 1)
pele(6, 12, 1, 5); pele(25, 12, 1, 5)  # orelhas
rect(22, 6, 3, 17, SOMBRA); rect(20, 23, 3, 1, SOMBRA); rect(25, 12, 1, 5, SOMBRA)
rect(8, 6, 1, 12, LUZ); rect(9, 5, 4, 1, LUZ)

# Contorno escuro em volta da cabeça para destacar
CONT = hexc("#140606")
for (x, y) in list(cabeca):
    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        q = (x + dx, y + dy)
        if q not in cabeca and 0 <= q[0] < N and 0 <= q[1] < N and q[1] < 24:
            px[q] = CONT

# Cabelo ralo
CAB = hexc("#26261e")
rect(8, 4, 5, 2, CAB); rect(15, 3, 3, 2, CAB); rect(20, 4, 4, 2, CAB); rect(8, 6, 2, 2, CAB); rect(23, 6, 1, 3, CAB)
# Cicatriz costurada na testa
rect(11, 8, 9, 1, hexc("#3c5a2c"))
for x in (12, 14, 16, 18): rect(x, 7, 1, 3, hexc("#2a3e20"))
# Sobrancelhas fundas
rect(9, 11, 5, 1, SOMBRA); rect(18, 11, 5, 1, SOMBRA)
# Olhos brilhando
for ox in (9, 18):
    rect(ox, 12, 5, 4, hexc("#160c06"))
    rect(ox + 1, 13, 3, 2, hexc("#ffd23a")); rect(ox + 2, 13, 1, 1, hexc("#fff8d0"))
# Nariz podre
rect(15, 16, 1, 2, hexc("#2c4520")); rect(17, 16, 1, 2, hexc("#2c4520"))
# Ferida no rosto
rect(20, 17, 2, 2, hexc("#8e1010")); rect(21, 17, 1, 1, hexc("#c42a2a"))
# Boca aberta com dentes e sangue
rect(10, 19, 12, 4, hexc("#2a0505")); rect(11, 23, 10, 1, hexc("#2a0505"))
DENTE = hexc("#efe7c8")
for x in (11, 13, 16, 18, 20): rect(x, 19, 1, 1 + (x % 2), DENTE)
for x in (12, 15, 19): rect(x, 22, 1, 1, DENTE)
SANGUE = hexc("#e53935")
rect(12, 23, 1, 4, SANGUE); rect(12, 27, 1, 1, hexc("#b71c1c"))
rect(19, 23, 1, 3, SANGUE)
rect(16, 24, 1, 2, hexc("#b71c1c"))

base = os.path.dirname(os.path.abspath(__file__))
for s in (192, 512):
    img.resize((s, s), Image.NEAREST).save(os.path.join(base, "..", "..", f"icon-{s}.png"))
img.resize((512, 512), Image.NEAREST).save(os.path.join(base, "preview.png"))
print("ok")
