//! Runs from the installer's temporary directory, never from the files it replaces.
#![windows_subsystem = "windows"]
use std::{ffi::c_void, path::Path, time::{Duration, Instant}};
type Handle = *mut c_void;
#[link(name = "kernel32")]
extern "system" {
    fn K32EnumProcesses(ids: *mut u32, size: u32, needed: *mut u32) -> i32;
    fn OpenProcess(access: u32, inherit: i32, pid: u32) -> Handle;
    fn QueryFullProcessImageNameW(process: Handle, flags: u32, name: *mut u16, size: *mut u32) -> i32;
    fn TerminateProcess(process: Handle, code: u32) -> i32;
    fn WaitForSingleObject(process: Handle, ms: u32) -> u32;
    fn CloseHandle(handle: Handle) -> i32;
}
struct Process(Handle);
impl Drop for Process { fn drop(&mut self) { unsafe { CloseHandle(self.0); } } }
fn normalize(path: &str) -> String {
    path.trim_start_matches(r"\\?\").replace('/', "\\").trim_end_matches('\\').to_lowercase()
}
fn belongs_to_install(image: &str, root: &str) -> bool {
    let image = normalize(image);
    image == format!(r"{root}\sztucode-desktop.exe")
        || image.starts_with(&format!(r"{root}\resources\runtime\"))
}
fn image(process: &Process) -> Option<String> {
    let mut name = vec![0u16; 32768];
    let mut size = name.len() as u32;
    if unsafe { QueryFullProcessImageNameW(process.0, 0, name.as_mut_ptr(), &mut size) } == 0 { return None; }
    Some(String::from_utf16_lossy(&name[..size as usize]))
}
fn stop_pass(root: &str) -> Result<usize, ()> {
    let mut ids = vec![0u32; 65536];
    let mut needed = 0;
    if unsafe { K32EnumProcesses(ids.as_mut_ptr(), (ids.len()*4) as u32, &mut needed) } == 0
        || needed as usize >= ids.len()*4 { return Err(()); }
    let mut stopped = 0;
    for &pid in &ids[..needed as usize/4] {
        if pid == 0 || pid == std::process::id() { continue; }
        // Match and terminate through the same handle, avoiding PID reuse races.
        let handle = unsafe { OpenProcess(0x1000 | 0x100000 | 1, 0, pid) };
        if handle.is_null() {
            let read = unsafe { OpenProcess(0x1000, 0, pid) };
            if !read.is_null() && image(&Process(read)).is_some_and(|p| belongs_to_install(&p, root)) { return Err(()); }
            continue;
        }
        let process = Process(handle);
        if !image(&process).is_some_and(|p| belongs_to_install(&p, root)) { continue; }
        if unsafe { WaitForSingleObject(handle, 0) } == 0 { continue; }
        if unsafe { TerminateProcess(handle, 0) } == 0 { return Err(()); }
        if unsafe { WaitForSingleObject(handle, 5000) } != 0 { return Err(()); }
        stopped += 1;
    }
    Ok(stopped)
}
fn run() -> Result<(), ()> {
    let arg = std::env::args().nth(1).ok_or(())?;
    let path = Path::new(&arg);
    if !path.is_absolute() || path.parent().is_none() { return Err(()); }
    // MSI passes INSTALLDIR with a trailing dot to preserve its final backslash.
    let root = if path.exists() { normalize(&path.canonicalize().map_err(|_| ())?.to_string_lossy()) }
        else { return Ok(()); };
    if Path::new(&root).parent().is_none() { return Err(()); }
    let deadline = Instant::now() + Duration::from_secs(15);
    let mut quiet = 0;
    while Instant::now() < deadline {
        match stop_pass(&root)? { 0 => quiet += 1, _ => quiet = 0 }
        if quiet >= 3 { return Ok(()); }
        std::thread::sleep(Duration::from_millis(200));
    }
    Err(())
}
fn main() { std::process::exit(if run().is_ok() { 0 } else { 1 }); }

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn scoped_to_the_selected_installation() {
        let root = normalize(r"E:\Work Station\SztuCode");
        assert!(belongs_to_install(r"E:\Work Station\SztuCode\resources\runtime\node.exe", &root));
        assert!(belongs_to_install(r"e:\work station\sztucode\sztucode-desktop.exe", &root));
        assert!(!belongs_to_install(r"E:\Work Station\SztuCode-other\resources\runtime\node.exe", &root));
        assert!(!belongs_to_install(r"C:\Program Files\nodejs\node.exe", &root));
        assert!(!belongs_to_install(r"E:\Work Station\SztuCode\project\node.exe", &root));
    }
}
