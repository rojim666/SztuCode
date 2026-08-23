//! macOS：工作区铺满/还原（分步 setFrame 跟手），并关闭 live-resize 内容保真。

use std::{
    collections::HashMap,
    sync::{
        atomic::{AtomicBool, Ordering},
        Mutex, OnceLock,
    },
    thread,
    time::Duration,
};

use objc2_app_kit::{NSScreen, NSView, NSWindow};
use objc2_foundation::{MainThreadMarker, NSPoint, NSRect, NSSize};
use tauri::WebviewWindow;

type FrameTuple = (f64, f64, f64, f64);

const ANIM_STEPS: u32 = 12;
const ANIM_STEP_MS: u64 = 18;

fn restore_frames() -> &'static Mutex<HashMap<usize, FrameTuple>> {
    static FRAMES: OnceLock<Mutex<HashMap<usize, FrameTuple>>> = OnceLock::new();
    FRAMES.get_or_init(|| Mutex::new(HashMap::new()))
}

fn animating() -> &'static AtomicBool {
    static FLAG: AtomicBool = AtomicBool::new(false);
    &FLAG
}

fn frame_to_tuple(frame: NSRect) -> FrameTuple {
    (
        frame.origin.x,
        frame.origin.y,
        frame.size.width,
        frame.size.height,
    )
}

fn tuple_to_frame(parts: FrameTuple) -> NSRect {
    NSRect {
        origin: NSPoint {
            x: parts.0,
            y: parts.1,
        },
        size: NSSize {
            width: parts.2,
            height: parts.3,
        },
    }
}

fn frames_near_equal(a: NSRect, b: NSRect) -> bool {
    const EPS: f64 = 2.0;
    (a.origin.x - b.origin.x).abs() < EPS
        && (a.origin.y - b.origin.y).abs() < EPS
        && (a.size.width - b.size.width).abs() < EPS
        && (a.size.height - b.size.height).abs() < EPS
}

fn window_key(ns_window: &NSWindow) -> usize {
    ns_window as *const NSWindow as usize
}

fn ease_out_cubic(t: f64) -> f64 {
    let u = 1.0 - t;
    1.0 - u * u * u
}

fn lerp_frame(from: FrameTuple, to: FrameTuple, t: f64) -> FrameTuple {
    (
        from.0 + (to.0 - from.0) * t,
        from.1 + (to.1 - from.1) * t,
        from.2 + (to.2 - from.2) * t,
        from.3 + (to.3 - from.3) * t,
    )
}

/// 关闭窗口 live-resize 内容保真，减轻拖边缘时边距跳变。
pub fn disable_live_resize_preserve(window: &WebviewWindow) -> Result<(), String> {
    let window_for_thread = window.clone();
    window
        .run_on_main_thread(move || {
            let Ok(ptr) = window_for_thread.ns_window() else {
                return;
            };
            if ptr.is_null() {
                return;
            }
            // SAFETY: ptr 来自 Tauri 主窗口的 ns_window，主线程上有效
            unsafe {
                let ns_window = &*(ptr as *const NSWindow);
                ns_window.setPreservesContentDuringLiveResize(false);
            }
        })
        .map_err(|e| e.to_string())
}

/// 将 contentView 与一层子视图 frame 对齐到 content bounds 并标记重绘。
fn sync_ns_window_content(ns_window: &NSWindow) {
    let Some(content) = ns_window.contentView() else {
        return;
    };
    let bounds = content.bounds();
    content.setNeedsDisplay(true);
    for sub in content.subviews().iter() {
        let sub_ref: &NSView = &*sub;
        let current = sub_ref.frame();
        if (current.origin.x - bounds.origin.x).abs() > 0.5
            || (current.origin.y - bounds.origin.y).abs() > 0.5
            || (current.size.width - bounds.size.width).abs() > 0.5
            || (current.size.height - bounds.size.height).abs() > 0.5
        {
            sub_ref.setFrame(bounds);
        }
        sub_ref.setNeedsDisplay(true);
    }
}

/// 在窗口 Resized 时强制 webview 跟 contentView 对齐到 bounds 并标记重绘。
pub fn sync_webview_to_content_view(window: &WebviewWindow) {
    if MainThreadMarker::new().is_some() {
        let Ok(ptr) = window.ns_window() else {
            return;
        };
        if ptr.is_null() {
            return;
        }
        // SAFETY: 主线程上调用 AppKit API
        unsafe {
            let ns_window = &*(ptr as *const NSWindow);
            sync_ns_window_content(ns_window);
        }
        return;
    }

    let window_for_thread = window.clone();
    let _ = window.run_on_main_thread(move || {
        let Ok(ptr) = window_for_thread.ns_window() else {
            return;
        };
        if ptr.is_null() {
            return;
        }
        // SAFETY: run_on_main_thread 保证在主线程上调用 AppKit API
        unsafe {
            let ns_window = &*(ptr as *const NSWindow);
            sync_ns_window_content(ns_window);
        }
    });
}

/// 在主线程上解析 toggle 的起止 frame；若无需动画返回 None。
fn resolve_toggle_frames(ns_window: &NSWindow) -> Option<(FrameTuple, FrameTuple)> {
    let mtm = MainThreadMarker::new()?;
    let screen = ns_window.screen().or_else(|| NSScreen::mainScreen(mtm))?;
    let visible = frame_to_tuple(screen.visibleFrame());
    let current = frame_to_tuple(ns_window.frame());
    let key = window_key(ns_window);
    let mut frames = restore_frames()
        .lock()
        .unwrap_or_else(|e| e.into_inner());

    if frames_near_equal(tuple_to_frame(current), tuple_to_frame(visible)) {
        let saved = frames.remove(&key)?;
        return Some((current, saved));
    }

    frames.insert(key, current);
    Some((current, visible))
}

/// 无动画写一帧（动画步进用）。
fn apply_frame(ns_window: &NSWindow, frame: FrameTuple) {
    ns_window.setFrame_display_animate(tuple_to_frame(frame), true, false);
}

/// 分步插值 setFrame，约 220ms，让 WKWebView 跟手。
fn animate_frame(window: WebviewWindow, from: FrameTuple, to: FrameTuple) {
    thread::spawn(move || {
        for step in 1..=ANIM_STEPS {
            let t = ease_out_cubic(f64::from(step) / f64::from(ANIM_STEPS));
            let frame = lerp_frame(from, to, t);
            let window_ref = window.clone();
            let window_for_frame = window.clone();
            let _ = window_ref.run_on_main_thread(move || {
                let Ok(ptr) = window_for_frame.ns_window() else {
                    return;
                };
                if ptr.is_null() {
                    return;
                }
                // SAFETY: ptr 来自 Tauri 主窗口的 ns_window，主线程上有效
                unsafe {
                    let ns_window = &*(ptr as *const NSWindow);
                    apply_frame(ns_window, frame);
                }
            });
            if step < ANIM_STEPS {
                thread::sleep(Duration::from_millis(ANIM_STEP_MS));
            }
        }
        animating().store(false, Ordering::SeqCst);
    });
}

/// 从 Tauri WebviewWindow 执行分步 work-area 切换；动画中忽略重复调用。
pub fn toggle_work_area(window: &WebviewWindow) -> Result<(), String> {
    if animating().swap(true, Ordering::SeqCst) {
        return Ok(());
    }

    let window_for_resolve = window.clone();
    let (tx, rx) = std::sync::mpsc::channel();
    window
        .run_on_main_thread(move || {
            let Ok(ptr) = window_for_resolve.ns_window() else {
                let _ = tx.send(None);
                return;
            };
            if ptr.is_null() {
                let _ = tx.send(None);
                return;
            }
            // SAFETY: ptr 来自 Tauri 主窗口的 ns_window，主线程上有效
            let frames = unsafe {
                let ns_window = &*(ptr as *const NSWindow);
                resolve_toggle_frames(ns_window)
            };
            let _ = tx.send(frames);
        })
        .map_err(|e| {
            animating().store(false, Ordering::SeqCst);
            e.to_string()
        })?;

    let Some((from, to)) = rx.recv().unwrap_or(None) else {
        animating().store(false, Ordering::SeqCst);
        return Ok(());
    };

    animate_frame(window.clone(), from, to);
    Ok(())
}
