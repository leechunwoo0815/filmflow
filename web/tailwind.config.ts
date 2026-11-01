import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        bg: "#0B0E13",
        panel: "#12161D",
        panel2: "#161B24",
        line: "#1F2630",
        txt: "#D7DEE8",
        dim: "#8A93A0",
        amber: "#F5A623",
        blue: "#4C8DFF",
        green: "#3FB950",
        red: "#F47067",
        purple: "#A371F7",
        cyan: "#39C5CF",
        gold: "#E3B341",
      },
    },
  },
  plugins: [],
};
export default config;
