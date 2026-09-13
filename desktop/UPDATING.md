# Desktop updates

Settings → About → Automatic updates checks for a release on demand. A second
click downloads and installs the signed package. Windows launches the installer
and exits; macOS/Linux offer a restart button after installation. The update
operation survives closing the settings dialog. Browser previews explain that
the desktop app is required.

This is a native Tauri distribution feature, independent of either daemon.
Ordinary development builds have no update endpoint or signing key and report
that online updates are not enabled. They do not report “up to date”.

## Enable for a release

1. Generate a Tauri signing key using `npm run tauri -- signer generate` from
   `desktop`. Store the private key outside the repository and back it up.
2. Create a release config override (for example `tauri.updater.json`):

   ```json
   {
     "bundle": { "createUpdaterArtifacts": true },
     "plugins": {
       "updater": {
         "pubkey": "YOUR_TAURI_PUBLIC_KEY",
         "endpoints": ["https://github.com/rojim666/SztuCode/releases/latest/download/latest.json"]
       }
     }
   }
   ```

3. Set `TAURI_SIGNING_PRIVATE_KEY` and `TAURI_SIGNING_PRIVATE_KEY_PASSWORD` in
   the release environment. Increment the desktop version consistently in
   `package.json`, `src-tauri/Cargo.toml`, and `src-tauri/tauri.conf.json`.
   Build with `npm run tauri -- build --config tauri.updater.json`.
4. Publish the generated updater artifacts and their `.sig` files. Publish a
   `latest.json` containing the version, optional notes, and a `platforms` map
   with entries such as `windows-x86_64`, `darwin-aarch64`, `linux-x86_64`.
   Each entry must contain the HTTPS artifact `url` and `signature` (the full
   contents of its `.sig` file). Only include platforms actually built. For
   Linux, use the AppImage updater artifact, not a deb package.
5. Install a signed older build that includes the same public key and endpoint,
   publish a newer signed release, and test check → download → install → restart
   on each target OS. Verify network failures and invalid signatures too.

The public key and endpoint must be included in the installed build, not only
in the newer release. Do not commit private keys or disable signature checking.
No releases or signing keys are created by this change.
