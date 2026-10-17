/// <reference types="vite/client" />

// M1：动态 import("./styles/fonts.css") 是副作用加载，告诉 TS 这是合法模块。
declare module "*.css";
