# Desktop updates

Settings → About → Automatic updates checks for a release on demand. A second
click downloads and installs the signed package. Windows launches the installer
and exits; macOS/Linux offer a restart button after installation. The update
operation survives closing the settings dialog. Browser previews explain that
the desktop app is required.

This is a native Tauri distribution feature, independent of either daemon.
The default config includes the public key and GitHub update endpoint. Installers
built before this was enabled need one manual reinstall using the new 1.0.3
installer. Future updates require a higher version, not a same-version rebuild.

## Signed Windows releases

Run `npm run release:windows --prefix desktop` from the repository root.
This builds Windows x64 EXE/MSI installers and their signatures, and writes
`latest.json` and `SHA256SUMS-v<version>.txt` into
`desktop/src-tauri/target/release/bundle`.
NSIS and MSI have separate update targets to preserve the installation type.

The local signing key is stored outside the repository at
`%LOCALAPPDATA%/SztuCode/release-keys/updater.key`. Back up this file securely;
all future releases need the same key. The local key has an empty password.
Use `SZTU_UPDATER_KEY_PATH` for another key location, or set
`TAURI_SIGNING_PRIVATE_KEY` and `TAURI_SIGNING_PRIVATE_KEY_PASSWORD` via CI secrets.
Never commit the private key or generate a new key for every release.

Before building, increment the desktop npm, Cargo and Tauri versions, sync the
lockfiles, and write `docs/releases/v<version>.md`. Upload both installers,
both `.sig` files and the checksum file to the matching GitHub Release first.
Upload `latest.json` last, then make the release latest. Verify the public
endpoint and test from an older signed installation.

Ordinary `tauri build` does not generate signatures. Use the signed command for
Windows releases. Only publish platform entries for artifacts actually built.

## Manual configuration for other platforms

1. Reuse the existing release signing key and configured public key on each
   platform. Store the private key outside the repository and back it up.
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
The repository contains only the public key. Keep the private key in secure
local storage or CI secrets.
