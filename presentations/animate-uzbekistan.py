"""Добавляет в .pptx объёмные переходы между слайдами и каскадное появление объектов."""
import re
import shutil
import sys
import zipfile
from pathlib import Path

SRC = Path(sys.argv[1] if len(sys.argv) > 1 else "Узбекистан.pptx")
DST = Path(sys.argv[2] if len(sys.argv) > 2 else "Узбекистан-3D.pptx")
WORK = Path("unpacked")

# объёмные переходы PowerPoint 2010+ (p14) с запасным вариантом для старых версий
P14 = "http://schemas.microsoft.com/office/powerpoint/2010/main"
MC = "http://schemas.openxmlformats.org/markup-compatibility/2006"

TRANS = [
    ('<p14:prism isInverted="0" isContent="1"/>', '<p:zoom dir="in"/>'),
    ('<p14:switch dir="r"/>', '<p:push dir="l"/>'),
    ('<p14:ferris dir="l"/>', '<p:push dir="l"/>'),
    ('<p14:gallery dir="r"/>', '<p:push dir="l"/>'),
    ('<p14:doors dir="vert"/>', '<p:split orient="vert" dir="out"/>'),
    ('<p14:flip dir="l"/>', '<p:push dir="l"/>'),
    ('<p14:window dir="horz"/>', '<p:split orient="horz" dir="out"/>'),
    ('<p14:conveyor dir="r"/>', '<p:push dir="l"/>'),
    ('<p14:vortex dir="r"/>', '<p:zoom dir="in"/>'),
    ('<p14:prism isInverted="1" isContent="1"/>', '<p:zoom dir="in"/>'),
]


def transition(i):
    """Один объёмный переход: в mc:Choice — 3D, в mc:Fallback — простой аналог."""
    three_d, plain = TRANS[i % len(TRANS)]
    return (
        f'<mc:AlternateContent xmlns:mc="{MC}">'
        f'<mc:Choice xmlns:p14="{P14}" Requires="p14">'
        f'<p:transition spd="slow" p14:dur="1100">{three_d}</p:transition>'
        f"</mc:Choice>"
        f'<mc:Fallback><p:transition spd="slow">{plain}</p:transition></mc:Fallback>'
        f"</mc:AlternateContent>"
    )


def effect(spid, delay, cid):
    """Появление объекта: проявление + подъём снизу (эффект «Выплывание»)."""
    return (
        f'<p:par><p:cTn id="{cid}" presetID="42" presetClass="entr" presetSubtype="0"'
        f' fill="hold" grpId="0" nodeType="withEffect">'
        f'<p:stCondLst><p:cond delay="{delay}"/></p:stCondLst><p:childTnLst>'
        f'<p:set><p:cBhvr><p:cTn id="{cid + 1}" dur="1" fill="hold">'
        f'<p:stCondLst><p:cond delay="0"/></p:stCondLst></p:cTn>'
        f'<p:tgtEl><p:spTgt spid="{spid}"/></p:tgtEl>'
        f"<p:attrNameLst><p:attrName>style.visibility</p:attrName></p:attrNameLst>"
        f'</p:cBhvr><p:to><p:strVal val="visible"/></p:to></p:set>'
        f'<p:anim calcmode="lin" valueType="num"><p:cBhvr additive="base">'
        f'<p:cTn id="{cid + 2}" dur="620" fill="hold"/>'
        f'<p:tgtEl><p:spTgt spid="{spid}"/></p:tgtEl>'
        f"<p:attrNameLst><p:attrName>ppt_y</p:attrName></p:attrNameLst></p:cBhvr>"
        f'<p:tavLst><p:tav tm="0"><p:val><p:strVal val="#ppt_y+.045"/></p:val></p:tav>'
        f'<p:tav tm="100000"><p:val><p:strVal val="#ppt_y"/></p:val></p:tav></p:tavLst></p:anim>'
        f'<p:animEffect transition="in" filter="fade"><p:cBhvr>'
        f'<p:cTn id="{cid + 3}" dur="620"/>'
        f'<p:tgtEl><p:spTgt spid="{spid}"/></p:tgtEl></p:cBhvr></p:animEffect>'
        f"</p:childTnLst></p:cTn></p:par>"
    )


def timing(spids, step=55):
    cid = 5
    effects = []
    for n, spid in enumerate(spids):
        effects.append(effect(spid, n * step, cid))
        cid += 4
    builds = "".join(f'<p:bldP spid="{s}" grpId="0" animBg="1"/>' for s in spids)
    return (
        "<p:timing><p:tnLst><p:par>"
        '<p:cTn id="1" dur="indefinite" restart="never" nodeType="tmRoot"><p:childTnLst>'
        '<p:seq concurrent="1" nextAc="seek">'
        '<p:cTn id="2" dur="indefinite" nodeType="mainSeq"><p:childTnLst>'
        '<p:par><p:cTn id="3" fill="hold"><p:stCondLst>'
        '<p:cond delay="indefinite"/>'
        '<p:cond evt="onBegin" delay="0"><p:tn val="2"/></p:cond>'
        "</p:stCondLst><p:childTnLst>"
        '<p:par><p:cTn id="4" fill="hold"><p:stCondLst><p:cond delay="0"/></p:stCondLst>'
        "<p:childTnLst>" + "".join(effects) + "</p:childTnLst></p:cTn></p:par>"
        "</p:childTnLst></p:cTn></p:par>"
        "</p:childTnLst></p:cTn>"
        '<p:prevCondLst><p:cond evt="onPrev" delay="0"><p:tgtEl><p:sldTgt/></p:tgtEl></p:cond></p:prevCondLst>'
        '<p:nextCondLst><p:cond evt="onNext" delay="0"><p:tgtEl><p:sldTgt/></p:tgtEl></p:cond></p:nextCondLst>'
        "</p:seq></p:childTnLst></p:cTn></p:par></p:tnLst>"
        f"<p:bldLst>{builds}</p:bldLst></p:timing>"
    )


def shape_ids(xml):
    """id всех фигур слайда в порядке отрисовки (без корневой группы)."""
    ids = []
    for sp in re.findall(r"<p:sp>.*?</p:sp>", xml, re.S):
        m = re.search(r'<p:cNvPr id="(\d+)"', sp)
        if m:
            ids.append(m.group(1))
    return ids


def main():
    if WORK.exists():
        shutil.rmtree(WORK)
    with zipfile.ZipFile(SRC) as z:
        z.extractall(WORK)

    slides = sorted(
        (WORK / "ppt" / "slides").glob("slide*.xml"),
        key=lambda p: int(re.search(r"\d+", p.name).group()),
    )
    for i, path in enumerate(slides):
        xml = path.read_text(encoding="utf-8")
        if "<p:transition" in xml or "<p:timing" in xml:
            raise SystemExit(f"{path.name}: анимация уже добавлена")
        ids = shape_ids(xml)
        block = transition(i) + timing(ids)
        xml = xml.replace("</p:sld>", block + "</p:sld>")
        path.write_text(xml, encoding="utf-8")
        print(f"{path.name}: переход + {len(ids)} объектов")

    if DST.exists():
        DST.unlink()
    with zipfile.ZipFile(DST, "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted(WORK.rglob("*")):
            if f.is_file():
                z.write(f, f.relative_to(WORK).as_posix())
    print("готово:", DST)


if __name__ == "__main__":
    main()
