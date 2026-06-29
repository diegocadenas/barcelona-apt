# Barcelona Apartment Finder

Hourly scanner for [Habitatge Jove](https://www.habitatgejove.com/webv2c/en/pisos.asp) student flats near Carrer de Provença 216, Barcelona.

## Features

- Filters 3+ bedroom flats within ~30 min walk of school
- Excludes Raval, Ciutat Vella, and L'Hospitalet
- Web dashboard with list + map views and month filters
- Optional hourly scan via macOS `launchd`

## Quick start

```bash
python3 scan_flats.py          # run scan → reports/latest.json
./open_dashboard.sh            # open http://localhost:8765
```

Edit `config.json` to adjust school location, room minimum, or excluded zones.

## Hourly scan (optional)

```bash
cp com.barcelona-apt.daily-scan.plist ~/Library/LaunchAgents/
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.barcelona-apt.daily-scan.plist
```
