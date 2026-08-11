const pptxgen = require(process.env.PPTX_LIB || "pptxgenjs");

const pres = new pptxgen();
pres.layout = "LAYOUT_WIDE"; // 13.333 x 7.5
pres.author = "Presentation";
pres.title = "Узбекистан — сердце Великого шёлкового пути";

const C = {
  ink: "0E2A47",
  inkCard: "17395C",
  blue: "1B6CA8",
  teal: "2A9D9D",
  gold: "D4A029",
  terra: "B5533C",
  light: "F1F6FA",
  white: "FFFFFF",
  muted: "5A6B7C",
  mutedDark: "A9BFD3",
};

const HEAD = "Cambria";
const BODY = "Calibri";

const W = 13.333;
const M = 0.7;
const CW = W - M * 2; // 11.933

/* ---------- helpers ---------- */

// восьмиконечная звезда (два наложенных квадрата) — сквозной визуальный мотив
function star(slide, cx, cy, size, color, transparency) {
  for (const rot of [0, 45]) {
    slide.addShape(pres.ShapeType.rect, {
      x: cx - size / 2,
      y: cy - size / 2,
      w: size,
      h: size,
      rotate: rot,
      fill: { color: color, transparency: transparency === undefined ? 0 : transparency },
      line: { type: "none" },
    });
  }
}

function starOutline(slide, cx, cy, size, color, transparency, thick) {
  for (const rot of [0, 45]) {
    slide.addShape(pres.ShapeType.rect, {
      x: cx - size / 2,
      y: cy - size / 2,
      w: size,
      h: size,
      rotate: rot,
      fill: { color: "FFFFFF", transparency: 100 },
      line: { color: color, width: thick || 1.25, transparency: transparency === undefined ? 0 : transparency },
    });
  }
}

function newSlide(dark) {
  const s = pres.addSlide();
  s.background = { color: dark ? C.ink : C.white };
  return s;
}

let pageNo = 0;
function header(slide, kicker, title, dark) {
  pageNo++;
  star(slide, M + 0.09, 0.63, 0.17, C.gold);
  slide.addText(kicker.toUpperCase(), {
    x: M + 0.32,
    y: 0.44,
    w: CW - 0.4,
    h: 0.35,
    fontFace: BODY,
    fontSize: 11.5,
    bold: true,
    charSpacing: 2.2,
    color: dark ? C.gold : C.terra,
    margin: 0,
    valign: "middle",
  });
  slide.addText(title, {
    x: M,
    y: 0.82,
    w: CW,
    h: 0.7,
    fontFace: HEAD,
    fontSize: 38,
    bold: true,
    color: dark ? C.white : C.ink,
    margin: 0,
    valign: "middle",
  });
  slide.addText(String(pageNo), {
    x: W - M - 0.7,
    y: 6.92,
    w: 0.7,
    h: 0.3,
    fontFace: BODY,
    fontSize: 10,
    color: dark ? C.mutedDark : "9AA9B6",
    align: "right",
    margin: 0,
  });
}

// вертикальная карточка: бейдж сверху, заголовок, текст
function cardV(slide, o) {
  slide.addShape(pres.ShapeType.roundRect, {
    x: o.x,
    y: o.y,
    w: o.w,
    h: o.h,
    rectRadius: 0.09,
    fill: { color: o.dark ? C.inkCard : C.light },
    line: { type: "none" },
    shadow: { type: "outer", color: "0E2A47", opacity: o.dark ? 0.35 : 0.13, blur: 10, offset: 2, angle: 90 },
  });
  slide.addShape(pres.ShapeType.ellipse, {
    x: o.x + 0.32,
    y: o.y + 0.3,
    w: 0.52,
    h: 0.52,
    fill: { color: o.accent || C.blue },
    line: { type: "none" },
  });
  slide.addText(o.badge, {
    x: o.x + 0.32,
    y: o.y + 0.3,
    w: 0.52,
    h: 0.52,
    fontFace: BODY,
    fontSize: 13,
    bold: true,
    color: C.white,
    align: "center",
    valign: "middle",
    margin: 0,
  });
  slide.addText(o.title, {
    x: o.x + 0.32,
    y: o.y + 0.95,
    w: o.w - 0.5,
    h: 0.62,
    fontFace: HEAD,
    fontSize: 16,
    bold: true,
    color: o.dark ? C.white : C.ink,
    margin: 0,
    valign: "top",
  });
  slide.addText(o.body, {
    x: o.x + 0.32,
    y: o.y + 1.6,
    w: o.w - 0.64,
    h: o.h - 1.85,
    fontFace: BODY,
    fontSize: 11.5,
    color: o.dark ? C.mutedDark : C.muted,
    lineSpacingMultiple: 1.1,
    margin: 0,
    valign: "top",
  });
}

// горизонтальная строка-карточка: бейдж слева, заголовок и текст справа
function rowCard(slide, o) {
  slide.addShape(pres.ShapeType.roundRect, {
    x: o.x,
    y: o.y,
    w: o.w,
    h: o.h,
    rectRadius: 0.08,
    fill: { color: o.dark ? C.inkCard : C.light },
    line: { type: "none" },
  });
  slide.addShape(pres.ShapeType.ellipse, {
    x: o.x + 0.26,
    y: o.y + (o.h - 0.5) / 2,
    w: 0.5,
    h: 0.5,
    fill: { color: o.accent || C.blue },
    line: { type: "none" },
  });
  slide.addText(o.badge, {
    x: o.x + 0.26,
    y: o.y + (o.h - 0.5) / 2,
    w: 0.5,
    h: 0.5,
    fontFace: BODY,
    fontSize: 11,
    bold: true,
    color: C.white,
    align: "center",
    valign: "middle",
    margin: 0,
  });
  slide.addText(
    [
      { text: o.title, options: { fontFace: HEAD, fontSize: 14.5, bold: true, color: o.dark ? C.white : C.ink, breakLine: true } },
      { text: o.body, options: { fontFace: BODY, fontSize: 11.5, color: o.dark ? C.mutedDark : C.muted } },
    ],
    {
      x: o.x + 0.92,
      y: o.y + 0.16,
      w: o.w - 1.2,
      h: o.h - 0.32,
      margin: 0,
      valign: "middle",
      lineSpacingMultiple: 1.05,
    }
  );
}

/* ============ 1. Титульный слайд ============ */
{
  const s = newSlide(true);
  starOutline(s, 12.1, 1.35, 2.4, C.gold, 62, 1.5);
  starOutline(s, 12.1, 1.35, 1.5, C.gold, 55, 1.5);
  starOutline(s, 1.15, 6.5, 1.9, C.teal, 68, 1.5);
  star(s, 11.35, 5.9, 0.5, C.terra, 45);
  star(s, 0.95, 1.15, 0.32, C.gold, 25);

  s.addText("ЦЕНТРАЛЬНАЯ АЗИЯ  ·  ВЕЛИКИЙ ШЁЛКОВЫЙ ПУТЬ", {
    x: M,
    y: 1.95,
    w: 9,
    h: 0.4,
    fontFace: BODY,
    fontSize: 13,
    bold: true,
    charSpacing: 3,
    color: C.gold,
    margin: 0,
    valign: "middle",
  });
  s.addText("УЗБЕКИСТАН", {
    x: M,
    y: 2.4,
    w: 10.5,
    h: 1.5,
    fontFace: HEAD,
    fontSize: 76,
    bold: true,
    color: C.white,
    charSpacing: 1,
    margin: 0,
    valign: "middle",
  });
  s.addText("Достопримечательности, главные туристические места\nи всё, что стоит знать о стране бирюзовых куполов", {
    x: M,
    y: 4.05,
    w: 9.6,
    h: 1.0,
    fontFace: BODY,
    fontSize: 19,
    color: C.mutedDark,
    lineSpacingMultiple: 1.25,
    margin: 0,
    valign: "top",
  });

  const chips = ["Самарканд", "Бухара", "Хива", "Ташкент"];
  let cx = M;
  chips.forEach((t) => {
    const w = 0.42 + t.length * 0.13;
    s.addShape(pres.ShapeType.roundRect, {
      x: cx,
      y: 5.5,
      w: w,
      h: 0.46,
      rectRadius: 0.22,
      fill: { color: C.white, transparency: 88 },
      line: { color: C.gold, width: 0.75, transparency: 45 },
    });
    s.addText(t, {
      x: cx,
      y: 5.5,
      w: w,
      h: 0.46,
      fontFace: BODY,
      fontSize: 12.5,
      color: C.white,
      align: "center",
      valign: "middle",
      margin: 0,
    });
    cx += w + 0.22;
  });
  s.addNotes("Приветствие. Узбекистан — страна на перекрёстке древних торговых путей, с четырьмя городами-музеями и 7 объектами Всемирного наследия ЮНЕСКО.");
}

/* ============ 2. Общие сведения ============ */
{
  const s = newSlide(false);
  header(s, "Знакомство со страной", "Общие сведения", false);

  const stats = [
    ["Ташкент", "Столица и крупнейший город (~3 млн жителей)"],
    ["≈ 37 млн", "Население — самое многочисленное в Центральной Азии"],
    ["448 978 км²", "Площадь территории страны"],
    ["Узбекский", "Государственный язык; русский широко используется"],
    ["Сум (UZS)", "Национальная валюта, введена в 1994 году"],
    ["7 объектов", "Включено в список Всемирного наследия ЮНЕСКО"],
  ];
  const cw = (CW - 0.6) / 3;
  const accents = [C.blue, C.teal, C.gold, C.terra, C.blue, C.teal];
  stats.forEach((st, i) => {
    const x = M + (i % 3) * (cw + 0.3);
    const y = 1.7 + Math.floor(i / 3) * 1.85;
    s.addShape(pres.ShapeType.roundRect, {
      x: x,
      y: y,
      w: cw,
      h: 1.6,
      rectRadius: 0.09,
      fill: { color: C.light },
      line: { type: "none" },
      shadow: { type: "outer", color: "0E2A47", opacity: 0.12, blur: 10, offset: 2, angle: 90 },
    });
    star(s, x + cw - 0.35, y + 0.32, 0.17, accents[i], 20);
    s.addText(st[0], {
      x: x + 0.32,
      y: y + 0.24,
      w: cw - 0.85,
      h: 0.6,
      fontFace: HEAD,
      fontSize: 25,
      bold: true,
      color: accents[i],
      margin: 0,
      valign: "middle",
    });
    s.addText(st[1], {
      x: x + 0.32,
      y: y + 0.86,
      w: cw - 0.6,
      h: 0.62,
      fontFace: BODY,
      fontSize: 11.5,
      color: C.muted,
      lineSpacingMultiple: 1.1,
      margin: 0,
      valign: "top",
    });
  });

  s.addShape(pres.ShapeType.roundRect, {
    x: M,
    y: 5.5,
    w: CW,
    h: 1.15,
    rectRadius: 0.09,
    fill: { color: C.ink },
    line: { type: "none" },
  });
  s.addText(
    [
      { text: "Уникальный факт:  ", options: { bold: true, color: C.gold } },
      {
        text: "Узбекистан — одна из двух стран мира (наряду с Лихтенштейном), которая дважды не имеет выхода к морю: её соседи тоже не имеют морских границ. Граничит с Казахстаном, Кыргызстаном, Таджикистаном, Афганистаном и Туркменистаном.",
        options: { color: C.white },
      },
    ],
    {
      x: M + 0.4,
      y: 5.5,
      w: CW - 0.8,
      h: 1.15,
      fontFace: BODY,
      fontSize: 12.5,
      lineSpacingMultiple: 1.15,
      margin: 0,
      valign: "middle",
    }
  );
  s.addNotes("Страна расположена между Амударьёй и Сырдарьёй. Административно: 12 областей, Республика Каракалпакстан и город Ташкент.");
}

/* ============ 3. История ============ */
{
  const s = newSlide(false);
  header(s, "Более двух тысяч лет истории", "Ключевые вехи", false);

  const eras = [
    ["IV в.\nдо н.э.", "Мараканда", "Александр Македонский покоряет Согдиану. Самарканд — ровесник Рима и Афин.", C.terra],
    ["IX–XII\nвв.", "Золотой век науки", "Аль-Хорезми (алгебра и алгоритм), Ибн Сина, Аль-Бируни — уроженцы этих земель.", C.blue],
    ["1220", "Нашествие Чингисхана", "Монголы разрушают цветущие города Мавераннахра.", C.muted],
    ["1370–\n1507", "Империя Тимуридов", "Амир Темур делает Самарканд столицей; при Улугбеке — расцвет астрономии.", C.gold],
    ["XVI–\nXIX вв.", "Эпоха ханств", "Бухарский эмират, Хивинское и Кокандское ханства — время великих караванов.", C.teal],
    ["1991", "Независимость", "1 сентября 1991 года провозглашена Республика Узбекистан.", C.terra],
  ];
  const cw = (CW - 0.4) / 2;
  eras.forEach((e, i) => {
    const x = M + (i % 2) * (cw + 0.4);
    const y = 1.68 + Math.floor(i / 2) * 1.72;
    s.addShape(pres.ShapeType.roundRect, {
      x: x,
      y: y,
      w: cw,
      h: 1.5,
      rectRadius: 0.09,
      fill: { color: C.light },
      line: { type: "none" },
    });
    s.addShape(pres.ShapeType.roundRect, {
      x: x + 0.25,
      y: y + 0.28,
      w: 1.12,
      h: 0.94,
      rectRadius: 0.08,
      fill: { color: e[3] },
      line: { type: "none" },
    });
    s.addText(e[0], {
      x: x + 0.25,
      y: y + 0.28,
      w: 1.12,
      h: 0.94,
      fontFace: BODY,
      fontSize: 12.5,
      bold: true,
      color: C.white,
      align: "center",
      valign: "middle",
      lineSpacingMultiple: 0.95,
      margin: 0,
    });
    s.addText(
      [
        { text: e[1], options: { fontFace: HEAD, fontSize: 15.5, bold: true, color: C.ink, breakLine: true } },
        { text: e[2], options: { fontFace: BODY, fontSize: 11.5, color: C.muted } },
      ],
      {
        x: x + 1.55,
        y: y + 0.22,
        w: cw - 1.85,
        h: 1.06,
        margin: 0,
        valign: "middle",
        lineSpacingMultiple: 1.08,
      }
    );
  });
  s.addNotes("История Узбекистана — это история Согдианы, Хорезма, Бактрии, арабского халифата, Саманидов, Тимуридов и трёх ханств.");
}

/* ============ 4. ЮНЕСКО ============ */
{
  const s = newSlide(false);
  header(s, "Всемирное наследие", "7 объектов ЮНЕСКО", false);

  const panelW = 3.7;
  s.addShape(pres.ShapeType.roundRect, {
    x: M,
    y: 1.68,
    w: panelW,
    h: 4.95,
    rectRadius: 0.1,
    fill: { color: C.ink },
    line: { type: "none" },
  });
  starOutline(s, M + panelW - 0.62, 6.15, 0.9, C.gold, 55, 1.25);
  s.addText("7", {
    x: M + 0.4,
    y: 1.95,
    w: panelW - 0.8,
    h: 1.5,
    fontFace: HEAD,
    fontSize: 96,
    bold: true,
    color: C.gold,
    margin: 0,
    valign: "middle",
  });
  s.addText("объектов Всемирного\nнаследия ЮНЕСКО", {
    x: M + 0.4,
    y: 3.35,
    w: panelW - 0.7,
    h: 0.9,
    fontFace: HEAD,
    fontSize: 16,
    bold: true,
    color: C.white,
    lineSpacingMultiple: 1.1,
    margin: 0,
    valign: "top",
  });
  s.addText(
    "Четыре объекта — памятники древних городов, три — природные и трансграничные. По числу сохранившихся памятников исламской архитектуры страна входит в число мировых лидеров.",
    {
      x: M + 0.4,
      y: 4.35,
      w: panelW - 0.8,
      h: 1.6,
      fontFace: BODY,
      fontSize: 12,
      color: C.mutedDark,
      lineSpacingMultiple: 1.15,
      margin: 0,
      valign: "top",
    }
  );

  const items = [
    ["1990", "Ичан-Кала (Хива)", "Внутренний город-крепость под открытым небом"],
    ["1993", "Исторический центр Бухары", "Более 140 памятников на средневековых улицах"],
    ["2000", "Исторический центр Шахрисабза", "Родина Амира Темура и дворец Ак-Сарай"],
    ["2001", "Самарканд — перекрёсток культур", "Регистан, Гур-Эмир, Шахи-Зинда, Афросиаб"],
    ["2016", "Западный Тянь-Шань", "Природный объект, общий с Казахстаном и Кыргызстаном"],
    ["2023", "Холодные зимние пустыни Турана", "Уникальные экосистемы пустынь Средней Азии"],
    ["2023", "Шёлковый путь: Зарафшан-Каракумский коридор", "Совместно с Таджикистаном и Туркменистаном"],
  ];
  const lx = M + panelW + 0.35;
  const lw = W - M - lx;
  items.forEach((it, i) => {
    const y = 1.68 + i * 0.72;
    s.addShape(pres.ShapeType.roundRect, {
      x: lx,
      y: y,
      w: lw,
      h: 0.62,
      rectRadius: 0.07,
      fill: { color: i < 4 ? C.light : "F6F3EC" },
      line: { type: "none" },
    });
    s.addShape(pres.ShapeType.roundRect, {
      x: lx + 0.2,
      y: y + 0.15,
      w: 0.72,
      h: 0.32,
      rectRadius: 0.06,
      fill: { color: i < 4 ? C.blue : C.teal },
      line: { type: "none" },
    });
    s.addText(it[0], {
      x: lx + 0.2,
      y: y + 0.15,
      w: 0.72,
      h: 0.32,
      fontFace: BODY,
      fontSize: 10,
      bold: true,
      color: C.white,
      align: "center",
      valign: "middle",
      margin: 0,
    });
    s.addText(
      [
        { text: it[1] + "  ", options: { fontFace: HEAD, fontSize: 13, bold: true, color: C.ink } },
        { text: it[2], options: { fontFace: BODY, fontSize: 10.5, color: C.muted } },
      ],
      {
        x: lx + 1.05,
        y: y,
        w: lw - 1.25,
        h: 0.62,
        margin: 0,
        valign: "middle",
      }
    );
  });
  s.addNotes("Первые объекты внесены в 1990-е, последние — в 2023 году в составе трансграничных номинаций Шёлкового пути.");
}

/* ============ 5. Регистан — главная достопримечательность ============ */
{
  const s = newSlide(true);
  header(s, "Достопримечательность № 1", "Площадь Регистан", true);
  starOutline(s, 12.35, 1.1, 2.2, C.gold, 65, 1.5);

  s.addText(
    "Ансамбль из трёх медресе в самом сердце Самарканда — символ Узбекистана и, по словам путешественников, самая красивая площадь Востока. Название означает «песчаное место»: здесь сходились шесть дорог, объявлялись указы и шумел главный базар города.",
    {
      x: M,
      y: 1.72,
      w: 8.4,
      h: 1.2,
      fontFace: BODY,
      fontSize: 14,
      color: C.mutedDark,
      lineSpacingMultiple: 1.2,
      margin: 0,
      valign: "top",
    }
  );

  const meds = [
    ["1417–1420", "Медресе Улугбека", "Старейшее здание ансамбля. Внук Тимура, астроном Улугбек, сам читал здесь лекции; фасад украшен звёздным орнаментом.", C.gold],
    ["1619–1636", "Медресе Шердор", "«Обитель львов»: на портале изображены тигрольвы с солнцем на спине — редкое для ислама изображение живых существ.", C.terra],
    ["1646–1660", "Медресе Тилля-Кари", "«Покрытое золотом»: в мечети под золотым куполом ушло около 3 кг сусального золота на отделку интерьера.", C.teal],
  ];
  const cw = (CW - 0.6) / 3;
  meds.forEach((m, i) => {
    const x = M + i * (cw + 0.3);
    cardV(s, {
      x: x,
      y: 3.15,
      w: cw,
      h: 2.65,
      badge: String(i + 1),
      accent: m[3],
      title: m[1],
      body: m[2],
      dark: true,
    });
    s.addText(m[0], {
      x: x + 0.95,
      y: 3.45,
      w: cw - 1.2,
      h: 0.3,
      fontFace: BODY,
      fontSize: 11,
      bold: true,
      color: m[3],
      margin: 0,
      valign: "middle",
    });
  });

  s.addText("Совет: приходите на закат — золотая отделка порталов светится, а вечером на площади включают подсветку и проводят светомузыкальное шоу.", {
    x: M,
    y: 6.05,
    w: CW,
    h: 0.5,
    fontFace: BODY,
    fontSize: 12.5,
    italic: true,
    color: C.gold,
    margin: 0,
    valign: "middle",
  });
  s.addNotes("Регистан формировался более двух столетий. Каждое медресе строил свой правитель, но ансамбль воспринимается как единое целое.");
}

/* ============ 6. Самарканд ============ */
{
  const s = newSlide(false);
  header(s, "Город № 1 для туриста", "Самарканд: что ещё увидеть", false);

  const items = [
    ["Гур-Эмир", "Мавзолей Амира Темура (1404) с ребристым бирюзовым куполом — прообраз Тадж-Махала.", C.blue],
    ["Биби-Ханым", "Соборная мечеть (1399–1404) после похода Тимура в Индию — одна из крупнейших в исламском мире.", C.terra],
    ["Шахи-Зинда", "Улица-некрополь из 11 мавзолеев XIV–XV вв. — самый красивый изразцовый ансамбль страны.", C.teal],
    ["Обсерватория Улугбека", "Остатки гигантского секстанта (1420-е): здесь измерили длину года почти без ошибки.", C.gold],
    ["Городище Афросиаб", "Древний Самарканд до монголов и музей с согдийскими фресками VII века.", C.blue],
    ["Сиабский базар", "Восточный рынок у мечети Биби-Ханым: лепёшки, сухофрукты, специи, халва.", C.terra],
  ];
  const cw = (CW - 0.6) / 3;
  items.forEach((it, i) => {
    cardV(s, {
      x: M + (i % 3) * (cw + 0.3),
      y: 1.68 + Math.floor(i / 3) * 2.6,
      w: cw,
      h: 2.45,
      badge: String(i + 1),
      accent: it[2],
      title: it[0],
      body: it[1],
    });
  });
  s.addNotes("Самарканд — второй по величине город страны, основан около VIII века до н. э. От Ташкента — 2 часа на скоростном поезде.");
}

/* ============ 7. Бухара ============ */
{
  const s = newSlide(false);
  header(s, "Священный город", "Бухара: город-музей", false);

  s.addText(
    [
      { text: "«Бухара-и-Шариф» — Благородная Бухара.  ", options: { bold: true, color: C.terra } },
      { text: "Более 140 памятников на компактной территории; центр целиком внесён в список ЮНЕСКО.", options: { color: C.muted } },
    ],
    { x: M, y: 1.56, w: CW, h: 0.34, fontFace: BODY, fontSize: 12.5, margin: 0, valign: "middle" }
  );

  const items = [
    ["Пои-Калян", "Минарет Калян (1127, 46 м), который пощадил Чингисхан, и медресе Мири Араб.", C.blue],
    ["Мавзолей Саманидов", "IX–X вв. — древнейший памятник города и шедевр кирпичной кладки.", C.teal],
    ["Крепость Арк", "Цитадель эмиров с тронным залом, монетным двором и музеями.", C.gold],
    ["Ляби-Хауз", "Старинный пруд с чайханами в тени тутовых деревьев.", C.terra],
    ["Чор-Минор", "Ворота медресе с четырьмя голубыми башенками — символ города.", C.blue],
    ["Торговые купола", "Средневековые крытые базары: ювелиры, менялы, шапочники.", C.teal],
  ];
  const cw = (CW - 0.6) / 3;
  items.forEach((it, i) => {
    cardV(s, {
      x: M + (i % 3) * (cw + 0.3),
      y: 1.98 + Math.floor(i / 3) * 2.44,
      w: cw,
      h: 2.36,
      badge: String(i + 1),
      accent: it[2],
      title: it[0],
      body: it[1],
    });
  });
  s.addNotes("В Бухаре стоит остановиться минимум на 2 дня: старый город удобно обходить пешком.");
}

/* ============ 8. Хива ============ */
{
  const s = newSlide(false);
  header(s, "Музей под открытым небом", "Хива: крепость Ичан-Кала", false);

  const panelW = 4.35;
  s.addShape(pres.ShapeType.roundRect, {
    x: M,
    y: 1.68,
    w: panelW,
    h: 4.9,
    rectRadius: 0.1,
    fill: { color: C.ink },
    line: { type: "none" },
  });
  starOutline(s, M + panelW - 0.62, 6.15, 0.95, C.teal, 55, 1.25);
  s.addText("Ичан-Кала", {
    x: M + 0.4,
    y: 2.0,
    w: panelW - 0.8,
    h: 0.5,
    fontFace: HEAD,
    fontSize: 26,
    bold: true,
    color: C.white,
    margin: 0,
    valign: "middle",
  });
  s.addText(
    "Внутренний город Хивы, окружённый глинобитной стеной длиной около 2,2 км и высотой до 10 м. Первый объект Узбекистана в списке ЮНЕСКО (1990).\n\nВнутри — более 50 памятников и около 250 старых домов, где по-прежнему живут люди. Кажется, что попал в средневековую восточную сказку: почти вся застройка сохранилась в первозданном виде.",
    {
      x: M + 0.4,
      y: 2.6,
      w: panelW - 0.8,
      h: 2.9,
      fontFace: BODY,
      fontSize: 12.5,
      color: C.mutedDark,
      lineSpacingMultiple: 1.18,
      margin: 0,
      valign: "top",
    }
  );

  const items = [
    ["Кальта-Минор", "Бирюзовый «короткий минарет» (1855): по замыслу хана — самый высокий в мире, но остался недостроенным.", C.teal],
    ["Минарет Ислам-Ходжа", "Самый высокий минарет страны — 57 м. С его вершины виден весь старый город.", C.gold],
    ["Джума-мечеть", "Мечеть без куполов и порталов: полумрак зала держат 213 резных деревянных колонн.", C.blue],
    ["Куня-Арк и Таш-Хаули", "Старая крепость правителей и роскошный дворец XIX века с изразцовыми айванами.", C.terra],
  ];
  const lx = M + panelW + 0.35;
  const lw = W - M - lx;
  items.forEach((it, i) => {
    rowCard(s, {
      x: lx,
      y: 1.68 + i * 1.3,
      w: lw,
      h: 1.15,
      badge: String(i + 1),
      accent: it[2],
      title: it[0],
      body: it[1],
    });
  });
  s.addNotes("Хива — самый дальний из трёх городов (около 450 км от Бухары). Между Бухарой и Хивой ходят поезда и такси через пустыню Кызылкум.");
}

/* ============ 9. Шахрисабз и Ферганская долина ============ */
{
  const s = newSlide(false);
  header(s, "За пределами «большой тройки»", "Шахрисабз и Ферганская долина", false);

  const halfW = (CW - 0.4) / 2;
  const cols = [
    {
      x: M,
      title: "Шахрисабз",
      sub: "Родина Амира Темура · ЮНЕСКО с 2000 г.",
      accent: C.terra,
      items: [
        ["Ак-Сарай", "«Белый дворец» Тимура: сохранились фрагменты портала высотой 38 м — когда-то он достигал 70 м."],
        ["Дорут-Тиловат", "Мемориальный комплекс с мавзолеями предков Тимура и мечетью Кок-Гумбаз."],
        ["Дорус-Сиадат", "Склеп, изначально построенный Тимуром как собственная усыпальница."],
      ],
    },
    {
      x: M + halfW + 0.4,
      title: "Ферганская долина",
      sub: "Центр ремёсел и самый плодородный край страны",
      accent: C.teal,
      items: [
        ["Коканд", "Дворец Худояр-хана с 19 залами и изразцовым фасадом — резиденция последних ханов."],
        ["Маргилан", "Столица шёлка: фабрика «Йодгорлик», где хан-атлас ткут и красят вручную."],
        ["Риштан", "Центр керамики: бело-голубая посуда из местной глины и природных красителей."],
      ],
    },
  ];
  cols.forEach((col) => {
    s.addShape(pres.ShapeType.roundRect, {
      x: col.x,
      y: 1.68,
      w: halfW,
      h: 0.95,
      rectRadius: 0.08,
      fill: { color: col.accent },
      line: { type: "none" },
    });
    s.addText(
      [
        { text: col.title, options: { fontFace: HEAD, fontSize: 21, bold: true, color: C.white, breakLine: true } },
        { text: col.sub, options: { fontFace: BODY, fontSize: 11.5, color: "FFFFFF" } },
      ],
      { x: col.x + 0.35, y: 1.68, w: halfW - 0.7, h: 0.95, margin: 0, valign: "middle", lineSpacingMultiple: 1.05 }
    );
    col.items.forEach((it, i) => {
      rowCard(s, {
        x: col.x,
        y: 2.82 + i * 1.34,
        w: halfW,
        h: 1.2,
        badge: String(i + 1),
        accent: col.accent,
        title: it[0],
        body: it[1],
      });
    });
  });
  s.addNotes("Шахрисабз находится в 90 км от Самарканда через горный перевал. Ферганская долина — восточная часть страны, 4-5 часов от Ташкента.");
}

/* ============ 10. Ташкент ============ */
{
  const s = newSlide(false);
  header(s, "Столица и точка входа", "Ташкент: древность и модерн", false);

  const items = [
    ["Хазрати Имам", "Религиозный центр столицы: здесь хранится Коран Османа VII века.", C.blue],
    ["Базар Чорсу", "Купольный рынок старого города: специи, сухофрукты, казаны с пловом.", C.terra],
    ["Медресе Кукельдаш", "Памятник XVI века рядом с Чорсу — редкое здание той эпохи в городе.", C.gold],
    ["Ташкентское метро", "Первое метро в Центральной Азии (1977): станции — подземные дворцы.", C.teal],
    ["Площадь Независимости", "Фонтаны, арка Эзгулик и мемориал Скорбящей матери в тенистых аллеях.", C.blue],
    ["Современный Ташкент", "Небоскрёбы Tashkent City, телебашня 375 м, лучшие рестораны страны.", C.terra],
  ];
  const cw = (CW - 0.6) / 3;
  items.forEach((it, i) => {
    cardV(s, {
      x: M + (i % 3) * (cw + 0.3),
      y: 1.68 + Math.floor(i / 3) * 2.6,
      w: cw,
      h: 2.45,
      badge: String(i + 1),
      accent: it[2],
      title: it[0],
      body: it[1],
    });
  });
  s.addNotes("Ташкент был почти полностью перестроен после землетрясения 1966 года, поэтому в нём соседствуют старый город и широкие советские проспекты.");
}

/* ============ 11. Природа ============ */
{
  const s = newSlide(true);
  header(s, "Не только архитектура", "Природа и активный отдых", true);
  starOutline(s, 12.9, 7.25, 1.8, C.teal, 68, 1.5);

  const items = [
    ["Чарвак и Чимган", "Бирюзовое водохранилище в горах Западного Тянь-Шаня в часе езды от Ташкента; зимой рядом работают горнолыжные склоны Чимгана и Бельдерсая.", C.teal],
    ["Пустыня Кызылкум", "Юртовые лагеря у озера Айдаркуль, ночёвка под звёздами, прогулки на верблюдах и древние караван-сараи по дороге в Хиву.", C.gold],
    ["Аральское море и Муйнак", "Знаменитое «кладбище кораблей» на бывшем дне моря — самый наглядный экологический урок XX века и плато Устюрт рядом.", C.terra],
    ["Горы Нуратау и Сармышсай", "Пешие маршруты, гостевые дома в горных кишлаках и ущелье с тысячами наскальных рисунков возрастом до 6000 лет.", C.blue],
  ];
  const cw = (CW - 0.6) / 2;
  items.forEach((it, i) => {
    cardV(s, {
      x: M + (i % 2) * (cw + 0.6),
      y: 1.72 + Math.floor(i / 2) * 2.5,
      w: cw,
      h: 2.3,
      badge: String(i + 1),
      accent: it[2],
      title: it[0],
      body: it[1],
      dark: true,
    });
  });
  s.addNotes("Более 4/5 территории — равнины и пустыни, но на востоке начинаются отроги Тянь-Шаня и Памиро-Алая с вершинами свыше 4000 м.");
}

/* ============ 12. Кухня ============ */
{
  const s = newSlide(false);
  header(s, "Гастрономия", "Узбекская кухня", false);

  const featW = 4.6;
  s.addShape(pres.ShapeType.roundRect, {
    x: M,
    y: 1.68,
    w: featW,
    h: 4.9,
    rectRadius: 0.1,
    fill: { color: C.terra },
    line: { type: "none" },
  });
  s.addText("Плов", {
    x: M + 0.4,
    y: 2.0,
    w: featW - 0.8,
    h: 0.7,
    fontFace: HEAD,
    fontSize: 34,
    bold: true,
    color: C.white,
    margin: 0,
    valign: "middle",
  });
  s.addText("Главное блюдо и часть национальной идентичности", {
    x: M + 0.4,
    y: 2.65,
    w: featW - 0.8,
    h: 0.5,
    fontFace: BODY,
    fontSize: 13,
    italic: true,
    color: "FFE9C9",
    margin: 0,
    valign: "top",
  });
  s.addText(
    "В 2016 году культура и традиции плова внесены в Список нематериального культурного наследия ЮНЕСКО.\n\nУ каждого региона свой рецепт: ташкентский, самаркандский, бухарский, ферганский, хорезмский. Готовят в казане на открытом огне, а на праздники — на сотни гостей.\n\nПопробовать стоит в «Центре плова» в Ташкенте — но только до обеда, вечером плов заканчивается.",
    {
      x: M + 0.4,
      y: 3.25,
      w: featW - 0.8,
      h: 2.6,
      fontFace: BODY,
      fontSize: 12.5,
      color: "FFEFE2",
      lineSpacingMultiple: 1.18,
      margin: 0,
      valign: "top",
    }
  );

  const dishes = [
    ["Самса", "Треугольные пирожки с мясом и луком из тандыра", C.gold],
    ["Шурпа и лагман", "Наваристый суп и тянутая лапша с овощами", C.blue],
    ["Манты и димлама", "Крупные паровые пельмени и томлёное рагу", C.teal],
    ["Нон", "Лепёшки из тандыра — в каждом городе свой узор", C.gold],
    ["Сумаляк", "Ритуальное блюдо из ростков пшеницы на Навруз", C.blue],
    ["Чай и сладости", "Зелёный чай, халва, нават, сухофрукты и орехи", C.teal],
  ];
  const lx = M + featW + 0.35;
  const lw = W - M - lx;
  const dw = (lw - 0.3) / 2;
  dishes.forEach((d, i) => {
    const x = lx + (i % 2) * (dw + 0.3);
    const y = 1.68 + Math.floor(i / 2) * 1.68;
    s.addShape(pres.ShapeType.roundRect, {
      x: x,
      y: y,
      w: dw,
      h: 1.5,
      rectRadius: 0.08,
      fill: { color: C.light },
      line: { type: "none" },
    });
    star(s, x + 0.42, y + 0.42, 0.22, d[2], 15);
    s.addText(d[0], {
      x: x + 0.68,
      y: y + 0.22,
      w: dw - 0.85,
      h: 0.4,
      fontFace: HEAD,
      fontSize: 15,
      bold: true,
      color: C.ink,
      margin: 0,
      valign: "middle",
    });
    s.addText(d[1], {
      x: x + 0.3,
      y: y + 0.68,
      w: dw - 0.6,
      h: 0.65,
      fontFace: BODY,
      fontSize: 11.5,
      color: C.muted,
      lineSpacingMultiple: 1.1,
      margin: 0,
      valign: "top",
    });
  });
  s.addNotes("Кухня основана на баранине, рисе, овощах и хлебе из тандыра. Обед в кафе обычно очень доступен по цене.");
}

/* ============ 13. Ремёсла и традиции ============ */
{
  const s = newSlide(false);
  header(s, "Живые традиции", "Ремёсла, праздники, гостеприимство", false);

  const items = [
    ["Сюзане", "Ручная вышивка с солярными кругами и цветами — приданое невесты.", C.terra],
    ["Керамика", "Школы Риштана (бело-голубая) и Гиждувана (тёплая охра) — своя палитра у каждой.", C.blue],
    ["Шёлк и хан-атлас", "Икат: нити красят до ткачества, поэтому узор «размытый». Центр — Маргилан.", C.gold],
    ["Навруз", "21 марта — праздник весны: сумаляк, игры, музыка и накрытые дворы.", C.teal],
    ["Чайхана и дастархан", "Гостя усаживают за дастархан и первым делом подают чай в пиале.", C.terra],
    ["Музыка и танец", "Макомы, дойра и карнай, хорезмский танец лазги — наследие ЮНЕСКО.", C.blue],
  ];
  const cw = (CW - 0.6) / 3;
  items.forEach((it, i) => {
    cardV(s, {
      x: M + (i % 3) * (cw + 0.3),
      y: 1.68 + Math.floor(i / 3) * 2.6,
      w: cw,
      h: 2.45,
      badge: String(i + 1),
      accent: it[2],
      title: it[0],
      body: it[1],
    });
  });
  s.addNotes("Ремёсла — важная часть туристического опыта: мастерские открыты для посещения, можно попробовать сделать что-то своими руками.");
}

/* ============ 14. Практическая информация ============ */
{
  const s = newSlide(false);
  header(s, "Полезно знать", "Маршрут и советы путешественнику", false);

  // маршрут
  s.addText("Классический маршрут на 8–10 дней", {
    x: M,
    y: 1.6,
    w: CW,
    h: 0.35,
    fontFace: HEAD,
    fontSize: 17,
    bold: true,
    color: C.ink,
    margin: 0,
    valign: "middle",
  });
  const route = [
    ["Ташкент", "2 дня"],
    ["Самарканд", "2–3 дня"],
    ["Шахрисабз", "1 день"],
    ["Бухара", "2 дня"],
    ["Хива", "1–2 дня"],
  ];
  const stepW = (CW - 4 * 0.45) / 5;
  route.forEach((r, i) => {
    const x = M + i * (stepW + 0.45);
    s.addShape(pres.ShapeType.roundRect, {
      x: x,
      y: 2.08,
      w: stepW,
      h: 1.0,
      rectRadius: 0.08,
      fill: { color: i % 2 === 0 ? C.blue : C.teal },
      line: { type: "none" },
    });
    s.addText(
      [
        { text: r[0], options: { fontFace: HEAD, fontSize: 15, bold: true, color: C.white, breakLine: true } },
        { text: r[1], options: { fontFace: BODY, fontSize: 11.5, color: "E4F1F6" } },
      ],
      { x: x, y: 2.08, w: stepW, h: 1.0, align: "center", valign: "middle", margin: 0, lineSpacingMultiple: 1.05 }
    );
    if (i < 4) {
      s.addText("›", {
        x: x + stepW,
        y: 2.08,
        w: 0.45,
        h: 1.0,
        fontFace: BODY,
        fontSize: 24,
        bold: true,
        color: "B9C7D2",
        align: "center",
        valign: "middle",
        margin: 0,
      });
    }
  });

  const tips = [
    ["Когда ехать", "Апрель–май и сентябрь–октябрь: тепло и цветёт. Летом бывает выше +40 °C, зимой прохладно и мало туристов.", C.gold],
    ["Виза", "Для граждан многих стран, включая Россию, Казахстан и большинство стран СНГ и ЕС, действует безвизовый режим.", C.blue],
    ["Транспорт", "Скоростные поезда «Афросиаб»: Ташкент — Самарканд около 2 ч, Ташкент — Бухара около 4 ч. Билеты берите заранее.", C.teal],
    ["Деньги и связь", "Валюта — сум; карты принимают в городах, но наличные нужны на базарах. Местная SIM-карта дешёвая и быстрая.", C.terra],
  ];
  const cw = (CW - 0.9) / 4;
  tips.forEach((t, i) => {
    const x = M + i * (cw + 0.3);
    s.addShape(pres.ShapeType.roundRect, {
      x: x,
      y: 3.5,
      w: cw,
      h: 2.35,
      rectRadius: 0.09,
      fill: { color: C.light },
      line: { type: "none" },
      shadow: { type: "outer", color: "0E2A47", opacity: 0.12, blur: 10, offset: 2, angle: 90 },
    });
    star(s, x + 0.45, 3.82, 0.26, t[2], 10);
    s.addText(t[0], {
      x: x + 0.32,
      y: 4.05,
      w: cw - 0.64,
      h: 0.4,
      fontFace: HEAD,
      fontSize: 16,
      bold: true,
      color: C.ink,
      margin: 0,
      valign: "middle",
    });
    s.addText(t[1], {
      x: x + 0.32,
      y: 4.5,
      w: cw - 0.64,
      h: 1.2,
      fontFace: BODY,
      fontSize: 11.5,
      color: C.muted,
      lineSpacingMultiple: 1.12,
      margin: 0,
      valign: "top",
    });
  });
  s.addText("Хорошая новость: между городами всё близко, а внутри старых центров всё обходится пешком.", {
    x: M,
    y: 6.05,
    w: CW,
    h: 0.45,
    fontFace: BODY,
    fontSize: 12.5,
    italic: true,
    color: C.terra,
    margin: 0,
    valign: "middle",
  });
  s.addNotes("Уточняйте визовые правила перед поездкой: условия периодически меняются.");
}

/* ============ 15. Итог ============ */
{
  const s = newSlide(true);
  starOutline(s, 11.9, 2.1, 2.6, C.gold, 62, 1.5);
  starOutline(s, 11.9, 2.1, 1.65, C.gold, 55, 1.5);

  s.addText("ПОЧЕМУ СТОИТ ПОЕХАТЬ", {
    x: M,
    y: 1.55,
    w: 8.5,
    h: 0.4,
    fontFace: BODY,
    fontSize: 12,
    bold: true,
    charSpacing: 3,
    color: C.gold,
    margin: 0,
    valign: "middle",
  });
  s.addText("Страна, где история\nещё живёт на улицах", {
    x: M,
    y: 2.05,
    w: 9.2,
    h: 1.7,
    fontFace: HEAD,
    fontSize: 42,
    bold: true,
    color: C.white,
    lineSpacingMultiple: 1.12,
    margin: 0,
    valign: "middle",
  });

  const reasons = [
    ["Наследие", "Четыре города-музея и 7 объектов ЮНЕСКО"],
    ["Доступность", "Безвизовый въезд и невысокие цены"],
    ["Гостеприимство", "Одна из самых радушных стран Азии"],
  ];
  const cw = (CW - 0.6) / 3;
  reasons.forEach((r, i) => {
    const x = M + i * (cw + 0.3);
    s.addShape(pres.ShapeType.roundRect, {
      x: x,
      y: 4.1,
      w: cw,
      h: 1.55,
      rectRadius: 0.09,
      fill: { color: C.inkCard },
      line: { type: "none" },
    });
    s.addText(r[0], {
      x: x + 0.32,
      y: 4.32,
      w: cw - 0.64,
      h: 0.42,
      fontFace: HEAD,
      fontSize: 17,
      bold: true,
      color: C.gold,
      margin: 0,
      valign: "middle",
    });
    s.addText(r[1], {
      x: x + 0.32,
      y: 4.8,
      w: cw - 0.64,
      h: 0.7,
      fontFace: BODY,
      fontSize: 12,
      color: C.mutedDark,
      lineSpacingMultiple: 1.12,
      margin: 0,
      valign: "top",
    });
  });

  s.addText("Спасибо за внимание!", {
    x: M,
    y: 6.05,
    w: CW,
    h: 0.5,
    fontFace: HEAD,
    fontSize: 20,
    bold: true,
    color: C.white,
    margin: 0,
    valign: "middle",
  });
  s.addNotes("Завершение: приглашение к вопросам.");
}

pres.writeFile({ fileName: process.argv[2] || "Uzbekistan.pptx" }).then((f) => console.log("Готово:", f));
