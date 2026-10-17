/** 一级导航与页面标题（2026-10-17 从 AppShell.tsx 抽出，M2 拆分）。 */
import { BookOpen, Library, Map, MessageCircle, NotebookPen, PenLine } from "lucide-react";

export const navItems = [
  { to: "/chat", label: "对话", icon: MessageCircle },
  { to: "/practice", label: "练习", icon: PenLine },
  { to: "/review", label: "复习", icon: BookOpen },
  { to: "/knowledge-map", label: "知识地图", icon: Map },
  { to: "/notes", label: "笔记", icon: NotebookPen },
  { to: "/library", label: "资料库", icon: Library },
];

export const pageMeta: Record<string, [string, string]> = {
  chat: ["学习对话", "今天想学什么？"],
  practice: ["主动练习", "用题目检验理解"],
  review: ["今日复习", "把薄弱点慢慢练熟"],
  library: ["本地资料", "你的学习材料"],
  "knowledge-map": ["知识地图", "概念关系一览"],
};
