# EOS Connect add-on (nanoBit93)

Home Assistant add-on packaging for the EOS Connect app source in this
repository. The add-on is built from a pinned snapshot of `src/` kept in this
repository at `eos_connect/src`.

- App source: `/src` at this repository's root
- Add-on source snapshot: `/eos_connect/src`
- CI: `home-assistant/builder` builds both architectures and publishes to GHCR
  on pushes to `main` (see `.github/workflows/ha_addon_builder.yml`)

Install via the Home Assistant add-on store by adding this repository URL:

```
https://github.com/nanoBit93/EOS_connect
```