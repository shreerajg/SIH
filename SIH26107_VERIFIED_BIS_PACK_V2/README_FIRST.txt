SIH26107 VERIFIED BIS SOURCE PACK V2 — SAFETY-CHECKED BOOTSTRAP

DO NOT USE THE OLDER ZIP.
This V2 fixes path/currentness/safety issues found during cross-checking.

WHAT THIS PACK DOES
- It does NOT change your database.
- It does NOT merge source manifests.
- It does NOT delete demo data.
- It downloads official BIS files into a new isolated folder only after validation.
- If any download fails validation, it safety-stops and does not promote the folder.

FASTEST SAFE USE
1. Extract this ZIP anywhere under C:\SIH (for example C:\SIH\BIS_PACK_V2).
2. Open PowerShell.
3. Run:
   cd C:\SIH\BIS_PACK_V2
   Set-ExecutionPolicy -Scope Process Bypass
   .\download_and_validate_verified_bis_corpus.ps1

Optional: include toys too:
   .\download_and_validate_verified_bis_corpus.ps1 -IncludeToys

4. On success it creates ONLY:
   C:\SIH\data\raw\verified_bis_2026_09_03\
   plus download_validation_report.json/csv inside that folder.
5. Then paste CLAUDE_SAFE_IMPORT_PROMPT.txt into Claude Code.

RECOMMENDED FOR YOUR DEADLINE
Use the default 3 golden scenarios first:
- Stationary storage electric water heater
- Domestic pressure cooker
- Two-wheeler helmet
Do not add toys unless the first 3 are working.
