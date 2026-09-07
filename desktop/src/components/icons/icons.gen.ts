// 图标数据来自 lucide 数据包（stroke 风格 IconNode），由 morphicons 消费渲染。
// key 沿用项目既有名称（原 lucide 图标名）；项目自造 key 以别名映射到最接近的 lucide 图标。
import {
  AlertCircle, AlertTriangle, AppWindow, Archive, ArrowLeft, ArrowRight, ArrowRightLeft, ArrowUp, ArrowUpRight,
  Beaker, BookOpen, Bot, Braces, Brain, BrainCircuit, CalendarClock, Check, CheckCircle2, ChevronDown, ChevronLeft, ChevronRight,
  Circle, CircleAlert, CircleDotDashed, CirclePlay, CirclePlus, CircleX, Clipboard, Clock, Clock3, Code, Code2, Coins, Copy, CornerDownLeft, CornerUpLeft, Cpu,
  Download, Edit3, Ellipsis, ExternalLink, Eye, EyeOff,
  FileClock, FileCode2, FileDiff, FileImage, FileLock2, FilePenLine, FileSearch, FileText, FileWarning, FileX2,
  Folder, FolderOpen, FolderPlus, Folders, GitBranch, GitCommitHorizontal, GitFork, Globe2,
  Image, Info, Languages, LayoutDashboard, Link2, ListChecks, ListOrdered, Loader2, LoaderCircle, LocateFixed,
  Maximize2, MessageCircle, MessageSquare, MessageSquarePlus, Minimize2, Minus, Monitor, Moon, MousePointer2, Music2,
  Network, Package, PackageOpen, Palette, PanelLeftClose, PanelLeftOpen, PanelRightClose, Paperclip, Pause, Pencil, Pin, PinOff,
  Play, Plug, Plus, Power, Presentation, Puzzle,
  Radio, RefreshCw, RotateCcw, RotateCw, ScrollText, Search, Server, Settings, Settings2, Share2, ShieldAlert, ShieldCheck,
  SlidersHorizontal, Sparkles, Square, SquareTerminal, Sun,
  Table2, Terminal, TerminalSquare, Timer, Trash2, Type,
  Unlink, Upload, Video, WandSparkles, Wrench, X, XCircle, ZoomIn, ZoomOut,
  // 项目自造 key → 最接近的 lucide 图标
  SquarePen as Compose,
  SquareCode as DevTools,
  Image as ImageIcon,
  Square as SquareShape,
  SquareCheck as SquareCheckbox,
} from "lucide";
import type { IconNode } from "morphicons/vue";

export const iconRegistry: Record<string, IconNode> = {
  AlertTriangle, AlertCircle, AppWindow, Archive, ArrowLeft, ArrowRight, ArrowRightLeft, ArrowUp, ArrowUpRight,
  Beaker, BookOpen, Bot, Braces, Brain, BrainCircuit, CalendarClock, Check, CheckCircle2, ChevronDown, ChevronLeft, ChevronRight,
  Circle, CircleAlert, CircleDotDashed, CirclePlay, CirclePlus, CircleX, Clipboard, Clock, Clock3, Code, Code2, Coins, Copy, CornerDownLeft, CornerUpLeft, Cpu,
  Compose, Download, Edit3, Ellipsis, ExternalLink, Eye, EyeOff,
  FileClock, FileCode2, FileDiff, FileImage, FileLock2, FilePenLine, FileSearch, FileText, FileWarning, FileX2,
  Folder, FolderOpen, FolderPlus, Folders, GitBranch, GitCommitHorizontal, GitFork, Globe2,
  Image, ImageIcon, Info, Languages, LayoutDashboard, Link2, ListChecks, ListOrdered, Loader2, LoaderCircle, LocateFixed,
  Maximize2, MessageCircle, MessageSquare, MessageSquarePlus, Minimize2, Minus, Monitor, Moon, MousePointer2, Music2,
  Network, Package, PackageOpen, Palette, PanelLeftClose, PanelLeftOpen, PanelRightClose, Paperclip, Pause, Pencil, Pin, PinOff,
  Play, Plug, Plus, Power, Presentation, Puzzle,
  Radio, RefreshCw, RotateCcw, RotateCw, ScrollText, Search, Server, Settings, Settings2, Share2, ShieldAlert, ShieldCheck,
  SlidersHorizontal, Sparkles, Square, SquareShape, SquareCheckbox, SquareTerminal, Sun,
  Table2, Terminal, TerminalSquare, Timer, Trash2, Type,
  Unlink, Upload, Video, WandSparkles, Wrench, X, XCircle, ZoomIn, ZoomOut,
  DevTools,
};
