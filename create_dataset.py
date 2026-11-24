from pathlib import Path

INBOX = Path("inbox")
INBOX.mkdir(exist_ok=True)

# Original 30 assignment files
filenames = [
    "925173_Lighting_Layout_RevA.dwg",
    "925173 - Fixture Schedule.xlsx",
    "Proposal_925180_Client.docx",
    "925180-site-photos.zip",
    "Rev2_Elevation_925173.pdf",
    "LCPL 925181 BOQ final.xlsx",
    "825104_concept_v3.psd",
    "concept_v4_825104.psd",
    "825104.pdf",
    "Meeting notes 925181.docx",
    "724112_Lighting Calc.pdf",
    "invoice_724112_and_925180.pdf",
    "624130_render_01.jpg",
    "624130_render_02.jpg",
    "Fixture_catalogue_2025.pdf",
    "125173_old_layout.dwg",
    "925042_draft.dwg",
    "Site visit 12-03-2025.jpg",
    "PO-9251800.pdf",
    "9251_misc.txt",
    "925181_Lighting_Layout_RevB.dwg",
    "925181_Lighting_Layout_RevB (1).dwg",
    "client email 925173.eml",
    "825110_section.dwg",
    "825110 section details.pdf",
    "Ph 9822012345 contact.txt",
    "724112_DIALux_export.pdf",
    "README.txt",
    "925190-final-FINAL.pdf",
    "625101_kickoff.pptx",
]

# Create original files.
for filename in filenames:
    file_path = INBOX / filename

    if filename == "925181_Lighting_Layout_RevB (1).dwg":
        # Exact duplicate of the original file.
        content = "925181_Lighting_Layout_RevB.dwg"

    else:
        content = filename

    file_path.write_text(content, encoding="utf-8")

# Additional 31st file with different content.
additional_file = INBOX / "925173_Lighting_Layout_RevA (1).dwg"
additional_file.write_text("revised", encoding="utf-8")

# Create the existing project folder and conflicting file.
existing_folder = Path("925173")
existing_folder.mkdir(exist_ok=True)

existing_file = existing_folder / "925173 - Fixture Schedule.xlsx"

if not existing_file.exists():
    existing_file.write_text("older version", encoding="utf-8")

print(f"Created {len(list(INBOX.iterdir()))} assignment files.")
print(f"Existing project file prepared: {existing_file}")