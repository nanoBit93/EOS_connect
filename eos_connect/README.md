# EOS Connect add-on (nanoBit93)

Home Assistant add-on packaging for the EOS Connect app source in this
repository. `src/` at the repository root is the application source; the build
workflow syncs it into the add-on folder before building.

- App source: `/src` at this repository's root
- Add-on packaging: `/eos_connect` (source synced in at build time)
- CI: `home-assistant/builder` builds both architectures and publishes to GHCR
  on pushes to `main` (see `.github/workflows/ha_addon_builder.yml`)

Install via the Home Assistant add-on store by adding this repository URL:

```
https://github.com/nanoBit93/EOS_connect
```