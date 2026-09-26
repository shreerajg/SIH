# Verified BIS import — dry-run mapping (2026-09-04)

Source pack: `SIH26107_VERIFIED_BIS_PACK_V2`
Downloaded + validated: `data/raw/verified_bis_2026_09_03/` (10/10 OK, SHA-256 recorded)

All content was independently verified by extracting text from each PDF and
confirming it matches the document the manifest claims — not merely that the
file is a valid PDF.

## Document mapping

| Local file | document_type | Identity | is_number | Existing record? |
|---|---|---|---|---|
| water_heater/IS_2082_2018_Product_Manual_Sep_2024.pdf | product_manual | IS-2082-2018-PM | IS 2082:2018 | NEW |
| water_heater/IS_302_Part2_Sec21_2024_Product_Manual_Sep_2024.pdf | product_manual | IS-302-P2S21-2024-PM | IS 302 (Part 2/Sec 21):2024 | NEW |
| water_heater/Domestic_Water_Heating_QCO_2025.pdf | qco | QCO-WATER-HEATING-2025 | — | NEW |
| pressure_cooker/IS_2347_2023_Product_Manual_Feb_2025.pdf | product_manual | IS-2347-2023-PM | IS 2347:2023 | NEW |
| pressure_cooker/Domestic_Pressure_Cooker_QCO_2020.pdf | qco | QCO-PRESSURE-COOKER-2020 | — | NEW |
| pressure_cooker/Domestic_Pressure_Cooker_QCO_Amendment_2020.pdf | qco | QCO-PRESSURE-COOKER-2020-AMD | — | NEW |
| helmet/IS_4151_2015_Product_Manual_Dec_2024.pdf | product_manual | IS-4151-2015-PM | IS 4151:2015 | NEW |
| helmet/Helmet_Two_Wheeler_QCO_2020.pdf | qco | QCO-HELMET-2020 | — | NEW |
| regulatory/Transition_Facilitation_QCO_2026.pdf | regulatory | QCO-TRANSITION-FACILITATION-2026 | — | NEW |
| regulatory/BIS_Current_Scheme_I_Compulsory_Certification.html | regulatory | BIS-SCHEME-I-INDEX | — | PROVENANCE ONLY — `.html` is not ingestible by the parser; registered as a source record, never parsed into clauses |

No existing record is reused or overwritten. All 8 `DEMO-STD-*` standards are untouched.

## Regulatory facts extracted from primary source text

| QCO | Notification | Notified | In force | Ministry | Standards named in its table |
|---|---|---|---|---|---|
| Electrical Appliances for domestic water heating (QC) Order, 2025 | S.O. 355(E) | 16 Jan 2025 | on Gazette publication (21 Jan 2025); implementation 1 Mar 2025 general / 1 Sep 2025 micro & small | Commerce & Industry (DPIIT) | IS 302 (Part 2/Sec 21):2018, IS 302 (Part 2/Sec 35):2017, IS 368:2014, **IS 2082:2018**, IS 17150:2019 |
| Domestic Pressure Cooker (QC) Order, 2020 | S.O. 294(E) | 21 Jan 2020 | 1 Aug 2020 | Commerce & Industry (DPIIT) | **IS 2347:2017** |
| Helmet for riders of Two Wheeler Motor Vehicles (QC) Order, 2020 | S.O. 4252(E) | 26 Nov 2020 | 1 Jun 2021 | Road Transport & Highways | **IS 4151:2015** |
| Transition Facilitation (QC) Order, 2026 | S.O. 3417(E) | 25 [month] 2026 | — | Commerce & Industry (DPIIT) | Facilitation mechanism affecting Toys QCO 2020 and domestic water heating QCO 2025 — **not** a blanket cancellation |

## Version conflicts to preserve (do NOT silently reconcile)

1. **Pressure cooker.** QCO 2020 table names `IS 2347:2017`. The current Product Manual
   (PM/IS 2347/9/February 2025) is for `IS 2347:2023`. The QCO states the latest
   BIS-notified version/amendments apply. Both editions are recorded; the transition is
   stated explicitly. This pack does **not** contain the 2024/2025 amendments to IS 2347:2023
   that BIS metadata indicates exist — so amendment coverage for this standard is incomplete
   and must be reported as such.
2. **Water heater.** QCO 2025 table names `IS 302 (Part 2/Sec 21):2018`, but the downloaded
   Product Manual is for `IS 302 (Part 2/Sec 21):2024 / IEC 60335-2-21:2022`. Recorded as a
   version transition, not merged.
3. **Helmet.** No conflict — QCO and Product Manual both reference `IS 4151:2015`.

## Scope limitation (must remain visible in the UI)

None of these documents is the full Indian Standard text. They are official Product Manuals,
Quality Control Orders and gazette notifications. Requirements, tests and clauses may only be
derived from what these documents actually contain. Where a full-standard requirement is not
present in the source, the platform must report `UNABLE_TO_VERIFY` / `OFFICIAL_VERIFICATION_REQUIRED`
rather than inventing it.
