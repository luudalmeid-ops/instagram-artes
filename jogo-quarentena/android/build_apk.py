#!/usr/bin/env python3
"""Monta o APK da Zona de Quarentena sem o Android SDK.

Usa só: javac (JDK), android-all.jar (Robolectric, Maven Central) como biblioteca de compilação,
dalvik-dx.jar (Maven Central) para gerar classes.dex, e Python com `cryptography` para assinar.
Gera à mão o AndroidManifest.xml binário e o resources.arsc (um único ícone).

Uso:
  python3 build_apk.py --android-all android-all.jar --dx dx.jar \
      --keystore chave.p12 --storepass SENHA --out ZonaDeQuarentena.apk
"""
import argparse, hashlib, io, os, shutil, struct, subprocess, tempfile, zipfile
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.serialization import pkcs12

HERE = os.path.dirname(os.path.abspath(__file__))
PACKAGE = "com.zonadequarentena.jogo"
LABEL = "Zona de Quarentena"
VERSION_CODE, VERSION_NAME = 3, "1.2"
MIN_SDK, TARGET_SDK = 21, 29

# IDs de atributos do framework (android.R.attr / android.R.style, API 29)
A = {"theme": 0x01010000, "label": 0x01010001, "icon": 0x01010002, "name": 0x01010003,
     "exported": 0x01010010, "screenOrientation": 0x0101001e, "configChanges": 0x0101001f,
     "minSdkVersion": 0x0101020c, "versionCode": 0x0101021b, "versionName": 0x0101021c,
     "targetSdkVersion": 0x01010270, "hardwareAccelerated": 0x010102d3}
THEME_FULLSCREEN = 0x0103000a  # Theme_Black_NoTitleBar_Fullscreen
ICON_ID = 0x7f010000           # drawable/icon (pacote 0x7f, tipo 1, entrada 0)
NS = "http://schemas.android.com/apk/res/android"
T_REF, T_STRING, T_DEC, T_HEX, T_BOOL = 0x01, 0x03, 0x10, 0x11, 0x12


# ---------- pools de strings ----------
def string_pool(strings, utf8=True):
    data, offsets = b"", []
    for s in strings:
        offsets.append(len(data))
        if utf8:
            b = s.encode("utf-8")
            assert len(s) < 128 and len(b) < 128
            data += bytes([len(s), len(b)]) + b + b"\0"
        else:
            data += struct.pack("<H", len(s)) + s.encode("utf-16-le") + b"\0\0"
    data += b"\0" * (-len(data) % 4)
    hdr = 28
    start = hdr + 4 * len(strings)
    size = start + len(data)
    flags = 0x100 if utf8 else 0
    return struct.pack("<HHIIIIII", 0x0001, hdr, size, len(strings), 0, flags, start, 0) + \
        b"".join(struct.pack("<I", o) for o in offsets) + data


# ---------- AndroidManifest.xml binário ----------
def manifest_axml():
    # (tag, [(nome, tipo, valor)], filhos)
    tree = ("manifest", [("package", T_STRING, PACKAGE), ("versionCode", T_DEC, VERSION_CODE), ("versionName", T_STRING, VERSION_NAME)], [
        ("uses-sdk", [("minSdkVersion", T_DEC, MIN_SDK), ("targetSdkVersion", T_DEC, TARGET_SDK)], []),
        ("uses-permission", [("name", T_STRING, "android.permission.INTERNET")], []),
        ("application", [("theme", T_REF, THEME_FULLSCREEN), ("label", T_STRING, LABEL), ("icon", T_REF, ICON_ID),
                         ("hardwareAccelerated", T_BOOL, True)], [
            ("activity", [("name", T_STRING, PACKAGE + ".MainActivity"), ("exported", T_BOOL, True),
                          ("screenOrientation", T_DEC, 1), ("configChanges", T_HEX, 0x4a0)], [
                ("intent-filter", [], [
                    ("action", [("name", T_STRING, "android.intent.action.MAIN")], []),
                    ("category", [("name", T_STRING, "android.intent.category.LAUNCHER")], []),
                ]),
            ]),
        ]),
    ])
    # Nomes de atributos do framework vêm primeiro, na ordem do mapa de recursos.
    attr_names = sorted({n for n in A}, key=lambda n: A[n])
    strings = list(attr_names)
    def idx(s):
        if s not in strings: strings.append(s)
        return strings.index(s)
    for s in ["android", NS, "package"]: idx(s)
    def collect(node):
        tag, attrs, kids = node
        idx(tag)
        for n, t, v in attrs:
            if t == T_STRING: idx(v)
        for k in kids: collect(k)
    collect(tree)

    chunks = []
    def node_chunks(node):
        tag, attrs, kids = node
        enc = []
        for n, t, v in attrs:
            ns = -1 if n == "package" else idx(NS)
            raw = idx(v) if t == T_STRING else -1
            data = idx(v) if t == T_STRING else (0xffffffff if (t == T_BOOL and v) else int(v))
            enc.append((A.get(n, 0), struct.pack("<iiiHBBI", ns, idx(n), raw, 8, 0, t, data)))
        enc.sort(key=lambda e: (e[0] == 0, e[0]))  # atributos do framework ordenados por ID
        body = struct.pack("<iiHHHHHH", -1, idx(tag), 20, 20, len(enc), 0, 0, 0) + b"".join(e[1] for e in enc)
        chunks.append(struct.pack("<HHIIi", 0x0102, 16, 16 + len(body), 1, -1) + body)
        for k in kids: node_chunks(k)
        chunks.append(struct.pack("<HHIIiii", 0x0103, 16, 24, 1, -1, -1, idx(tag)))
    node_chunks(tree)

    ns_start = struct.pack("<HHIIiii", 0x0100, 16, 24, 1, -1, idx("android"), idx(NS))
    ns_end = struct.pack("<HHIIiii", 0x0101, 16, 24, 1, -1, idx("android"), idx(NS))
    pool = string_pool(strings)
    resmap = struct.pack("<HHI", 0x0180, 8, 8 + 4 * len(attr_names)) + b"".join(struct.pack("<I", A[n]) for n in attr_names)
    body = pool + resmap + ns_start + b"".join(chunks) + ns_end
    return struct.pack("<HHI", 0x0003, 8, 8 + len(body)) + body


# ---------- resources.arsc com um único drawable ----------
def resources_arsc():
    gpool = string_pool(["res/drawable/icon.png"])
    tpool = string_pool(["drawable"], utf8=False)
    kpool = string_pool(["icon"], utf8=False)
    spec = struct.pack("<HHIBBHI", 0x0202, 16, 16 + 4, 1, 0, 0, 1) + struct.pack("<I", 0)
    config = struct.pack("<I", 64) + b"\0" * 60
    hdr = 8 + 12 + len(config)
    entry = struct.pack("<HHI", 8, 0, 0) + struct.pack("<HBBI", 8, 0, T_STRING, 0)
    typ = struct.pack("<HHIBBHII", 0x0201, hdr, hdr + 4 + len(entry), 1, 0, 0, 1, hdr + 4) + config + struct.pack("<I", 0) + entry
    name = PACKAGE.encode("utf-16-le").ljust(256, b"\0")
    phdr = 288
    pkg_body = tpool + kpool + spec + typ
    pkg = struct.pack("<HHII", 0x0200, phdr, phdr + len(pkg_body), 0x7f) + name + \
        struct.pack("<IIIII", phdr, 1, phdr + len(tpool), 1, 0) + pkg_body
    body = gpool + pkg
    return struct.pack("<HHII", 0x0002, 12, 12 + len(body), 1) + body


# ---------- zip alinhado ----------
def write_zip(path, entries):
    with zipfile.ZipFile(path, "w") as z:
        for name, data, stored in entries:
            info = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_STORED if stored else zipfile.ZIP_DEFLATED
            if stored:
                pos = z.fp.tell() + 30 + len(name.encode()) + 6
                pad = -pos % 4
                info.extra = struct.pack("<HHH", 0xd935, 2 + pad, 4) + b"\0" * pad
            z.writestr(info, data)


# ---------- assinatura v2 ----------
def lp(b): return struct.pack("<I", len(b)) + b

def sign_v2(apk, key, cert_der):
    data = open(apk, "rb").read()
    eocd = data.rfind(b"PK\x05\x06")
    cd_size, cd_off = struct.unpack("<II", data[eocd + 12:eocd + 20])
    sections = [data[:cd_off], data[cd_off:cd_off + cd_size], data[eocd:]]
    chunks = []
    for sec in sections:
        for i in range(0, len(sec), 1 << 20):
            c = sec[i:i + (1 << 20)]
            chunks.append(hashlib.sha256(b"\xa5" + struct.pack("<I", len(c)) + c).digest())
    digest = hashlib.sha256(b"\x5a" + struct.pack("<I", len(chunks)) + b"".join(chunks)).digest()
    ALG = 0x0103  # RSASSA-PKCS1-v1_5 com SHA-256
    signed = lp(lp(struct.pack("<I", ALG) + lp(digest))) + lp(lp(cert_der)) + lp(b"")
    sig = key.sign(signed, padding.PKCS1v15(), hashes.SHA256())
    pub = key.public_key().public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
    signer = lp(signed) + lp(lp(struct.pack("<I", ALG) + lp(sig))) + lp(pub)
    value = lp(lp(signer))
    pair = struct.pack("<Q", 4 + len(value)) + struct.pack("<I", 0x7109871a) + value
    size = len(pair) + 8 + 16
    block = struct.pack("<Q", size) + pair + struct.pack("<Q", size) + b"APK Sig Block 42"
    new_eocd = bytearray(sections[2])
    struct.pack_into("<I", new_eocd, 16, cd_off + len(block))
    open(apk, "wb").write(sections[0] + block + sections[1] + bytes(new_eocd))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--android-all", required=True)
    ap.add_argument("--dx", required=True)
    ap.add_argument("--keystore", required=True)
    ap.add_argument("--storepass", required=True)
    ap.add_argument("--alias", default="zona")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()

    tmp = tempfile.mkdtemp()
    classes = os.path.join(tmp, "classes"); os.makedirs(classes)
    src = os.path.join(HERE, "src", *PACKAGE.split("."), "MainActivity.java")
    subprocess.run(["javac", "--release", "8", "-nowarn", "-cp", a.android_all, "-d", classes, src], check=True)
    dex = os.path.join(tmp, "classes.dex")
    subprocess.run(["java", "-cp", a.dx, "com.android.dx.command.Main", "--dex", "--output=" + dex, classes], check=True)

    html = open(os.path.join(HERE, "..", "index.html"), encoding="utf-8").read()
    icon = open(os.path.join(HERE, "..", "icon-192.png"), "rb").read()
    unsigned = os.path.join(tmp, "unsigned.apk")
    write_zip(unsigned, [
        ("AndroidManifest.xml", manifest_axml(), False),
        ("classes.dex", open(dex, "rb").read(), False),
        ("resources.arsc", resources_arsc(), True),
        ("res/drawable/icon.png", icon, True),
        ("assets/index.html", html.encode("utf-8"), False),
    ])

    # v1 (jarsigner) para Android 5 e 6, depois v2 por cima para Android 7+.
    subprocess.run(["jarsigner", "-keystore", a.keystore, "-storetype", "PKCS12", "-storepass", a.storepass,
                    "-digestalg", "SHA-256", "-sigalg", "SHA256withRSA", unsigned, a.alias],
                   check=True, stdout=subprocess.DEVNULL)
    key, cert, _ = pkcs12.load_key_and_certificates(open(a.keystore, "rb").read(), a.storepass.encode())
    sign_v2(unsigned, key, cert.public_bytes(serialization.Encoding.DER))
    shutil.copy(unsigned, a.out)
    print("APK:", a.out, os.path.getsize(a.out), "bytes")


if __name__ == "__main__":
    main()
