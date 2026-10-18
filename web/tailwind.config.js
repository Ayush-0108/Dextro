/** Warm, sophisticated palette: sand canvas, white cards, espresso text, emerald/cobalt/amber evidence accents. */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        sand: { 50: "#FAF7F2", 100: "#F7F4EE", line: "#E7E2D8", wire: "#A8A29E" },
        ink: { DEFAULT: "#1C1917", body: "#44403C", muted: "#78716C" },
        ok: { DEFAULT: "#059669", soft: "#ECFDF5", line: "#A7F3D0" },
        derive: { DEFAULT: "#2563EB", soft: "#EFF6FF", line: "#BFDBFE" },
        warn: { DEFAULT: "#D97706", soft: "#FFFBEB", line: "#FDE68A" },
        bad: { DEFAULT: "#DC2626", soft: "#FEF2F2", line: "#FECACA" },
      },
      fontFamily: {
        sans: ["Inter", "-apple-system", "SF Pro Text", "system-ui", "sans-serif"],
        mono: ["JetBrains Mono", "Fira Code", "ui-monospace", "monospace"],
      },
      boxShadow: { card: "0 1px 3px rgba(28,25,23,.06), 0 1px 2px rgba(28,25,23,.04)", float: "0 8px 30px rgba(120,113,108,.18)" },
    },
  },
  plugins: [],
};
