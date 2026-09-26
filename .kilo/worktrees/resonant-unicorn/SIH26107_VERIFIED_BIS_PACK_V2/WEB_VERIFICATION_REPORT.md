# SIH26107 BIS Source Pack V2 — Cross-check Report

Cross-checked on 2026-09-03 against current official BIS pages returned by BIS.

## Important fixes from the older pack
1. **ZIP path bug fixed:** the older ZIP nested the script under `SIH26107_verified_corpus/` while README told the user to run it from `C:\SIH`. V2 locates the repository root safely even when extracted in a subfolder.
2. **Pressure cooker manual updated:** older pack used a 2024 URL. Current BIS Product Manuals page points to `PM/IS 2347/9/February 2025` at `https://www.bis.gov.in/wp-content/uploads/2025/02/PM-IS-2347.pdf`.
3. **Toy manual updated:** older pack used a 2021 manual. Current BIS Product Manuals page points to the November 2023 manual at `https://www.bis.gov.in/wp-content/uploads/2023/11/PM-9873-Nov-2023.pdf`.
4. **2026 regulatory context added:** current BIS Scheme-I page links `Transition Facilitation (Quality Control) Order, 2026` for Toys and domestic water heating. V2 downloads it as a separate regulatory document.
5. **Silent failures removed:** older downloader caught failures and continued to print `Done`. V2 records every download and exits with a safety stop if any source fails.
6. **Content validation added:** V2 checks allow-listed BIS hosts, minimum size, real `%PDF-` magic for PDFs, and BIS-related HTML content before promoting downloads.
7. **Premature verification fixed:** V2 manifest does not claim ingestion verification before files are actually downloaded and validated.
8. **No automatic merge:** V2 never modifies the project's live manifest, DB or vector store. Claude is instructed to dry-run the mapping first and Git-checkpoint before broad changes.

## Official source checks
- BIS current Product Manuals page lists **IS 2082:2018** Stationary storage type electric water heaters and links the Sep 2024 manual.
- BIS current Product Manuals page lists **IS 2347:2023** Domestic Pressure Cooker and links the Feb 2025 manual.
- BIS current Product Manuals page lists **IS 4151:2015** Protective Helmet for Two Wheeler Riders and links the Dec 2024 manual.
- BIS current Product Manuals page lists **IS 9873 Parts 1,2,3,4,7,9 and IS 15644** Safety of Toys and links the Nov 2023 manual.
- BIS current Scheme-I compulsory-certification page lists pressure cooker, toys, helmet, and domestic-water-heating entries and their QCO links.
- BIS Standard Details currently marks **IS 2082:2018** as Mandatory Certification and reviewed/reaffirmed in 2026.
- BIS Standard Details currently marks **IS 2347:2023** Domestic Pressure Cooker as Mandatory Certification and shows three amendments (2024, 2025, 2025). V2 therefore explicitly prevents Claude from claiming the pack contains all IS 2347 amendments.
- The official 2026 Transition Facilitation Order includes Toys QCO 2020 and Electrical appliance for domestic water heating QCO 2025 in its schedule. It is modeled as a special facilitation mechanism, not a blanket cancellation.

## Scope limitation
This pack intentionally does **not** redistribute or pretend to contain full paid/copyrighted Indian Standard texts. Product Manuals and QCOs are official supporting/regulatory documents and can support a strong verified SIH demo, but RAG must label their document type accurately.
