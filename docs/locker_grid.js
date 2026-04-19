/** @schema 2.10
 * @input startNumber: number = 1
 * @input cols: number = 12
 * @input rows: number = 7
 * @input cellWidth: number = 46
 * @input cellHeight: number = 66
 * @input gap: number = 2
 */

const start = Math.floor(pencil.input.startNumber);
const cols  = Math.floor(pencil.input.cols);
const rows  = Math.floor(pencil.input.rows);
const cw    = pencil.input.cellWidth;
const ch    = pencil.input.cellHeight;
const gap   = pencil.input.gap;

const STATES = {
  active:   { bg:"#DCFCE7", border:"#BBF7D0", num:"#166534", name:"#14532D", sub:"#16A34A" },
  imminent: { bg:"#FEE2E2", border:"#FECACA", num:"#7F1D1D", name:"#991B1B", sub:"#DC2626" },
  expired:  { bg:"#F9FAFB", border:"#D1D5DB", num:"#9CA3AF", name:"#6B7280", sub:"#9CA3AF" },
  holding:  { bg:"#F5F3FF", border:"#DDD6FE", num:"#5B21B6", name:"#6D28D9", sub:"#7C3AED" },
  empty:    { bg:"#F3F4F6", border:"#E5E7EB", num:"#D1D5DB", name:"#9CA3AF", sub:"#D1D5DB" },
};

// 데모용 샘플 이름
const NAMES = ["김민준","이서연","박지훈","최수아","정도윤","강하은","조현우","윤지아","장민서","임채원","한예린","오태양","서지우","권나연","문승현"];
const DAYS  = ["89일","210일","33일","155일","45일","360일","77일","120일","15일","300일","55일","180일","8일","240일","6일"];

function getState(n) {
  const r = (n * 37 + 17) % 100;
  if (r < 45) return "empty";
  if (r < 68) return "active";
  if (r < 78) return "expired";
  if (r < 88) return "imminent";
  return "holding";
}

const nodes = [];

for (let row = 0; row < rows; row++) {
  for (let col = 0; col < cols; col++) {
    // 열-우선(column-major) 번호: 최상단 최좌측=start, 아래로 증가
    const num   = start + col * rows + row;
    const state = getState(num);
    const c     = STATES[state];
    const x     = col * (cw + gap);
    const y     = row * (ch + gap);

    const nameText  = state === "empty" || state === "expired"
      ? (state === "expired" ? NAMES[num % NAMES.length] : "")
      : state === "holding" ? NAMES[num % NAMES.length]
      : NAMES[num % NAMES.length];

    const subText = state === "empty"   ? "빈 칸"
      : state === "expired"  ? "만료"
      : state === "holding"  ? "홀딩"
      : state === "imminent" ? DAYS[num % DAYS.length]
      : DAYS[num % DAYS.length];

    nodes.push({
      type: "frame",
      x, y,
      width: cw,
      height: ch,
      fill: c.bg,
      stroke: { fill: c.border, thickness: 1 },
      cornerRadius: 3,
      layout: "none",
      children: [
        {
          type: "text",
          x: 0, y: 3,
          content: String(num),
          fontSize: 8,
          fontWeight: "700",
          fill: c.num,
          textGrowth: "fixed-width-height",
          width: cw,
          height: 11,
          textAlign: "center",
        },
        {
          type: "text",
          x: 2, y: 16,
          content: nameText,
          fontSize: 9,
          fontWeight: "700",
          fill: c.name,
          textGrowth: "fixed-width-height",
          width: cw - 4,
          height: 26,
          textAlign: "center",
        },
        {
          type: "text",
          x: 0, y: 46,
          content: subText,
          fontSize: 8,
          fill: c.sub,
          textGrowth: "fixed-width-height",
          width: cw,
          height: 11,
          textAlign: "center",
        },
      ],
    });
  }
}

return nodes;
