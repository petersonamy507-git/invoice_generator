import openpyxl
import os
import sys
import zipfile
from datetime import datetime, timedelta
import re  # For sanitizing file names
import json
import requests
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Add the s3-bucket-upload directory to the Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 's3-bucket-upload'))

try:
    from s3_upload_helper import S3UploadHelper
    S3_AVAILABLE = True
except ImportError:
    S3_AVAILABLE = False
    print("Warning: S3 upload helper not available. Files will not be uploaded to S3.")

# List of fixed headers and their respective days for list items
header_days_mapping = {
    "Identity Designing": {
        "* Brand Identity/Guidline Design": 2,
        "* Logo Design (6 Variations)": 5,
        "* Animated Logo": 3,
    },
    "Social Media Management": {
        "* SM Calender (1 Month)": 4,
        "* SM Post Designs": 10,
        "* Social Media Posting": 6,
        "* SM Accounts Creation": 3,
        "* Copyrighting (Content)": 4,
        "* Monthly Reporting and Insights": 3,
    },
    "Website Designing & Development": {
        "* UI/UX Design (Figma)": 6,
        "* Logo Design": 3,
        "* Domain & Hosting": 2,
        "* SSL": 2,
        "Chat Integration / User ($24)": 2,
        "* Copyrighting (Content)": 5,
        "* Social Media Posts": 4,
        "* Webmaster tool (Basic)": 2,
        "* Analytics (Basic)": 2,
    },
    "Brand Guideline & Graphics Designing": {
        "* Brand Identity/Guidline Design": 6,
        "* Logo Design (6 Variations)": 3,
        "* Animated Logo": 2,
        "* Stationery Design (LetterHead, Cards etc...)": 2,
        "* Social Media Assets": 2,
        "* Packaging Design": 5,
        "* Print and Digital Collateral (Flyers, Brochures etc..)": 4,
    },
    "App Designing & Development": {
        "* Prototype Development": 15,
        "* App UI/UX Design (Figma)": 15,
        "* Backend Development": 45,
        "* Frontend Development": 45,
        "* Quality Assurance and Testing": 10,
        "* Deployment and App Store Submission": 5,
        "* Security and Compliance": 5,
        "* Logo Design": 2,
        "* Domain & Hosting": 2,
        "* SSL": 2,
        "* Copyrighting (Content)": 5,
        "* Social Media Posts": 7,
        "* Webmaster tool (Basic)": 9,
        "* Analytics (Basic)": 9,
    },
    "Penetration Testing (Web)": {
        "* Web/App Application Penetration Testing": 8,
        "* Social Engineering Testing": 6,
        "* Red Team Exercises": 6,
        "* Compliance and Regulatory Testing (PCI etc..)": 5,
        "* Reporting and Remediation": 5,
    },
    "Penetration Testing (App)": {
        "* Web/App Application Penetration Testing": 12,
        "* Social Engineering Testing": 9,
        "* Red Team Exercises": 9,
        "* Compliance and Regulatory Testing (PCI etc..)": 8,
        "* Reporting and Remediation": 7,
    },
    "Dev Operations": {
        "* Implement CI/CD pipelines": 5,
        "* Containerization": 5,
        "* Monitoring and Logging": 5,
        "* Security Automation": 5,
        "* Load Balancing": 4,
        "* Disaster Recovery and High Availability": 4,
        "* Virtual Training and Consultation": 2,
    },
}
# Fixed headers
fixed_headers = [
    "Identity Designing", "Social Media Management", "Brand Guideline & Graphics Designing", 
    "Website Designing & Development", "App Designing & Development", "Penetration Testing (Web)", 
    "Dev Operations", "Penetration Testing (App)"
]

# Function to generate dummy content (simplified version without OpenAI)
def generate_dummy_content(prompt: str, max_tokens: int = 400) -> str:
    return f"Dummy content for: {prompt}\n\nThis is a placeholder file generated for testing purposes.\n"

# Function to extract data from the uploaded Excel file
def extract_data_from_excel(file_path, fixed_headers):
    # Remove leading/trailing spaces from the file path
    file_path = file_path.strip()
    
    workbook = openpyxl.load_workbook(file_path)
    sheet = workbook.active

    data = []
    current_header = None
    current_points = []
    
    # Extract the Invoice number, "To", "From", "To Company" and "From Company" from fixed locations
    invoice_no = sheet["A1"].value  # Invoice no. is in cell A1
    to = sheet["B2"].value         # "To" is taken from B2
    from_value = sheet["C2"].value # "From" is taken from C2
    to_company = sheet["D2"].value  # "To Company" is taken from D2
    from_company = sheet["E2"].value  # "From Company" is taken from E2
    
    # Loop through the rows in the sheet and gather headers and points
    for row in sheet.iter_rows(min_row=1, max_row=sheet.max_row, min_col=1, max_col=sheet.max_column, values_only=True):
        for cell in row:
            if isinstance(cell, str):  # Only work with strings
                # Check if the cell matches a header
                cell_stripped = cell.strip()
                # Remove "Brand Guideline &  Graphics Designing" extra space issue
                if "Brand Guideline" in cell_stripped and "Graphics Designing" in cell_stripped:
                    cell_stripped = "Brand Guideline & Graphics Designing"
                
                if cell_stripped in fixed_headers:
                    # If points exist, store them under the last header
                    if current_points:
                        data.append({"header": current_header, "points": current_points})
                    current_header = cell_stripped
                    current_points = []
                elif cell_stripped and current_header and cell_stripped.startswith("*"):  # Collect points only if they start with *
                    current_points.append(cell_stripped)

    # After the last header, add the remaining points
    if current_points:
        data.append({"header": current_header, "points": current_points})

    return data, invoice_no, to, from_value, to_company, from_company

# Function to sanitize filenames by replacing invalid characters
def sanitize_filename(filename: str) -> str:
    # Replace invalid characters with underscores
    return re.sub(r'[<>:"/\\|?*]', '_', filename)

# Map list items to file extensions (based on list item, this can be adjusted as needed)
def map_to_file_extension(header, point):
    if "Penetration Testing" in header:
        return ".txt"  # Placeholder for penetration testing content
    elif "App Designing" in header or "Website Designing" in header:
        return ".html"  # Placeholder for design-related content
    elif "Dev Operations" in header:
        return ".py"  # Placeholder for code content
    elif "Social Media" in header:
        return ".docx"  # Placeholder for social media strategy document
    return ".txt"  # Default to text for anything else

# Function to write the extracted data into a new Excel file with Timeline, Sort, Date, To, From, To Company, From Company
def write_to_excel(extracted_data, output_file_path, invoice_no, to, from_value, to_company, from_company, zip_paths_map, invoice_pdf_url="", contract_pdf_url=""):
    structured_data = []
    serial_no = 1
    today = datetime.today()

    # Loop through the extracted data to create the structured format
    for entry in extracted_data:
        header = entry["header"]
        points = entry["points"]

        # Sort the points based on Timeline (Days)
        sorted_points = sorted(points, key=lambda p: header_days_mapping.get(header, {}).get(p, float('inf')))

        # Assign sort numbers based on the sorted order
        sort_serial_no = 1
        for point in sorted_points:
            days = header_days_mapping.get(header, {}).get(point, None)
            if days:
                # Each item delivers on Day 1 + its own duration (not cumulative)
                date_value = today + timedelta(days=days)
                # Get the ZIP path for this deliverable
                zip_path = zip_paths_map.get(f"{header}_{point}", "")
                # Add invoice and contract PDF URLs to each row
                structured_data.append([invoice_no, header, point, days, sort_serial_no, date_value.strftime("%Y-%m-%d"), to, from_value, to_company, from_company, zip_path, invoice_pdf_url, contract_pdf_url])
                serial_no += 1
            sort_serial_no += 1

    # Create a new Excel workbook and add data
    output_workbook = openpyxl.Workbook()
    output_sheet = output_workbook.active
    output_sheet.append(["Invoice no.", "Main Item", "Line Item", "Timeline (Days)", "Sort", "Date", "To", "From", "To Company", "From Company", "ZIP Path", "Invoice PDF", "Contract PDF", "Status 1", "Status 2"])  # Add headers

    # Add the rows with the structured data
    for row in structured_data:
        output_sheet.append(row)

    # Save the output file with a unique name (using timestamp to avoid conflicts)
    output_workbook.save(output_file_path)
    print(f"Formatted data saved to: {output_file_path}")
    return output_file_path

# Function to generate the necessary files based on headers and list items
def generate_files_for_list_items(extracted_data, deliverables_base_folder):
    # Create the main deliverables directory
    os.makedirs(deliverables_base_folder, exist_ok=True)

    # Dictionary to store ZIP paths for each deliverable
    zip_paths_map = {}

    # Process each entry (header with points)
    for entry in extracted_data:
        header = entry["header"]
        points = entry["points"]

        # Generate content for each point (list item)
        for point in points:
            # Create a unique folder for this deliverable
            deliverable_key = f"{header}_{point}"
            sanitized_folder_name = sanitize_filename(deliverable_key.replace(' ', '_'))
            deliverable_folder = os.path.join(deliverables_base_folder, sanitized_folder_name)
            os.makedirs(deliverable_folder, exist_ok=True)

            prompt = f"Generate a dummy file for {point} in the domain of {header}."
            dummy_content = generate_dummy_content(prompt)

            # Debugging: check if content was generated
            if not dummy_content:
                print(f"Warning: No content generated for: {point}")

            # Determine the file extension based on the header and list item
            extension = map_to_file_extension(header, point)

            # Create a sanitized filename for the point with dummy content in the folder
            sanitized_filename = sanitize_filename(f"{point.replace(' ', '_')}{extension}")
            file_path = os.path.join(deliverable_folder, sanitized_filename)

            # Write the content to the file
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(dummy_content)

            # Create a ZIP file for this deliverable folder
            zip_filename = f"{sanitized_folder_name}.zip"
            zip_path = os.path.join(deliverables_base_folder, zip_filename)

            with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                # Add all files from the deliverable folder to the zip
                for root, dirs, files in os.walk(deliverable_folder):
                    for file in files:
                        file_full_path = os.path.join(root, file)
                        arcname = os.path.relpath(file_full_path, deliverable_folder)
                        zipf.write(file_full_path, arcname=arcname)

            # Store the ZIP path in the map
            zip_paths_map[deliverable_key] = zip_path
            print(f"Created deliverable folder: {deliverable_folder}")
            print(f"Created ZIP file: {zip_path}")

    return zip_paths_map

# Function to upload ZIP files to S3 and update Excel with S3 URLs
def upload_zips_to_s3_and_update_excel(excel_file_path, s3_prefix="deliverables", invoice_pdf_url="", contract_pdf_url=""):
    """Upload all ZIP files to S3 and update the Excel file with S3 URLs."""
    if not S3_AVAILABLE:
        print("\n⚠ S3 upload is not available. Skipping S3 upload.")
        return {"total": 0, "successful": 0, "failed": 0, "skipped": 0}

    print(f"\n{'='*60}")
    print(f"UPLOADING ZIP FILES TO S3")
    print(f"{'='*60}\n")

    workbook = openpyxl.load_workbook(excel_file_path)
    sheet = workbook.active

    headers = [cell.value for cell in sheet[1]]
    zip_path_col_index = headers.index("ZIP Path") + 1

    # Get Invoice PDF and Contract PDF column indices
    invoice_pdf_col_index = None
    contract_pdf_col_index = None
    if "Invoice PDF" in headers:
        invoice_pdf_col_index = headers.index("Invoice PDF") + 1
    if "Contract PDF" in headers:
        contract_pdf_col_index = headers.index("Contract PDF") + 1

    try:
        s3_helper = S3UploadHelper()
        print(f"✓ S3 helper initialized - Bucket: {s3_helper.bucket_name}\n")
    except Exception as e:
        print(f"✗ Failed to initialize S3: {e}\n")
        return {"total": 0, "successful": 0, "failed": 0, "skipped": 0}

    results = {"total": 0, "successful": 0, "failed": 0, "skipped": 0}

    for row_num in range(2, sheet.max_row + 1):
        zip_path_cell = sheet.cell(row=row_num, column=zip_path_col_index)
        zip_path = zip_path_cell.value

        if not zip_path or not isinstance(zip_path, str):
            results["skipped"] += 1
            continue

        results["total"] += 1

        if not os.path.exists(zip_path):
            print(f"✗ Row {row_num}: File not found")
            results["failed"] += 1
            continue

        line_item = sheet.cell(row=row_num, column=3).value
        print(f"Uploading: {line_item}")

        try:
            result = s3_helper.upload_file(
                file_path=zip_path,
                s3_prefix=s3_prefix,
                custom_filename=os.path.splitext(os.path.basename(zip_path))[0]
            )

            if result["success"]:
                zip_path_cell.value = result["file_url"]
                print(f"  ✓ {result['file_url']}\n")
                results["successful"] += 1
            else:
                print(f"  ✗ {result.get('error', 'Unknown error')}\n")
                results["failed"] += 1
        except Exception as e:
            print(f"  ✗ {str(e)}\n")
            results["failed"] += 1

        # Update Invoice PDF and Contract PDF columns with S3 URLs
        if invoice_pdf_col_index and invoice_pdf_url:
            sheet.cell(row=row_num, column=invoice_pdf_col_index).value = invoice_pdf_url
        if contract_pdf_col_index and contract_pdf_url:
            sheet.cell(row=row_num, column=contract_pdf_col_index).value = contract_pdf_url

    workbook.save(excel_file_path)

    print(f"{'='*60}")
    print(f"S3 Upload Summary: {results['successful']}/{results['total']} successful")
    if invoice_pdf_url:
        print(f"Invoice PDF URL: {invoice_pdf_url}")
    if contract_pdf_url:
        print(f"Contract PDF URL: {contract_pdf_url}")
    print(f"{'='*60}\n")

    return results


# Function to send data to webhook
def send_to_webhook(excel_file_path, invoice_pdf_url="", contract_pdf_url=""):
    """Read Excel file and send data to webhook as JSON."""
    webhook_url = os.getenv("WEBHOOK_URL")

    if not webhook_url:
        print("\n⚠️ Webhook URL not configured in .env file")
        return {"success": False, "error": "Webhook URL not configured"}

    print(f"\n{'='*60}")
    print(f"SENDING DATA TO WEBHOOK")
    print(f"{'='*60}\n")
    print(f"Webhook URL: {webhook_url}")

    try:
        # Read Excel file
        workbook = openpyxl.load_workbook(excel_file_path)
        sheet = workbook.active

        # Get headers
        headers = [cell.value for cell in sheet[1]]

        # Build JSON data
        rows_data = []
        for row_num in range(2, sheet.max_row + 1):
            row_dict = {}
            for col_num, header in enumerate(headers, start=1):
                cell_value = sheet.cell(row=row_num, column=col_num).value
                # Convert date objects to string
                if isinstance(cell_value, datetime):
                    cell_value = cell_value.strftime("%Y-%m-%d")
                row_dict[header] = cell_value
            rows_data.append(row_dict)

        # Create payload
        payload = {
            "invoice_pdf_url": invoice_pdf_url,
            "contract_pdf_url": contract_pdf_url,
            "total_deliverables": len(rows_data),
            "deliverables": rows_data,
            "processed_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }

        # Send to webhook
        print(f"Sending {len(rows_data)} deliverables to webhook...")
        response = requests.post(
            webhook_url,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=30
        )

        if response.status_code in [200, 201, 202]:
            print(f"✓ Webhook sent successfully!")
            print(f"  Status: {response.status_code}")
            print(f"  Response: {response.text[:200]}")
            return {
                "success": True,
                "status_code": response.status_code,
                "response": response.text
            }
        else:
            print(f"✗ Webhook failed with status {response.status_code}")
            print(f"  Response: {response.text[:200]}")
            return {
                "success": False,
                "status_code": response.status_code,
                "error": response.text
            }

    except requests.exceptions.RequestException as e:
        print(f"✗ Webhook request failed: {e}")
        return {"success": False, "error": str(e)}
    except Exception as e:
        print(f"✗ Error preparing webhook data: {e}")
        return {"success": False, "error": str(e)}
    finally:
        print(f"{'='*60}\n")


# Main function to process the file and generate output with files in a zip
def process_file_and_generate_zip(file_path, upload_to_s3=False, s3_prefix="deliverables", invoice_pdf_path=None, contract_pdf_path=None, upload_to_sheets=False):
    # Step 1: Extract data from the uploaded file
    extracted_data, invoice_no, to, from_value, to_company, from_company = extract_data_from_excel(file_path, fixed_headers)
    print("Extracted Data:", extracted_data)

    # Step 2: Create a timestamped folder for the deliverables
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    # Create deliverables folder in the same directory as the input file
    base_dir = os.path.dirname(file_path) if os.path.dirname(file_path) else '.'
    deliverables_folder = os.path.join(base_dir, "deliverables", f"deliverables_{timestamp}")

    # Step 3: Generate the files and create individual zips for each deliverable
    zip_paths_map = generate_files_for_list_items(extracted_data, deliverables_folder)

    # Step 4: Upload PDFs to S3 if provided and S3 upload is enabled
    invoice_pdf_url = ""
    contract_pdf_url = ""

    if upload_to_s3 and S3_AVAILABLE:
        try:
            s3_helper = S3UploadHelper()

            # Upload Invoice PDF
            if invoice_pdf_path and os.path.exists(invoice_pdf_path):
                print(f"\n📄 Uploading Invoice PDF to S3...")
                invoice_result = s3_helper.upload_file(
                    file_path=invoice_pdf_path,
                    s3_prefix=s3_prefix,
                    custom_filename=f"{invoice_no}_Invoice"
                )
                if invoice_result["success"]:
                    invoice_pdf_url = invoice_result["file_url"]
                    print(f"  ✓ Invoice PDF uploaded: {invoice_pdf_url}")
                else:
                    print(f"  ✗ Invoice PDF upload failed: {invoice_result.get('error', 'Unknown error')}")

            # Upload Contract PDF
            if contract_pdf_path and os.path.exists(contract_pdf_path):
                print(f"\n📄 Uploading Contract PDF to S3...")
                contract_result = s3_helper.upload_file(
                    file_path=contract_pdf_path,
                    s3_prefix=s3_prefix,
                    custom_filename=f"{invoice_no}_Contract"
                )
                if contract_result["success"]:
                    contract_pdf_url = contract_result["file_url"]
                    print(f"  ✓ Contract PDF uploaded: {contract_pdf_url}")
                else:
                    print(f"  ✗ Contract PDF upload failed: {contract_result.get('error', 'Unknown error')}")

        except Exception as e:
            print(f"\n⚠️ Error uploading PDFs to S3: {e}")

    # Step 5: Write the extracted data into a new Excel file (with a unique name) in the deliverables folder
    excel_output_path = os.path.join(deliverables_folder, f"formatted_output_{timestamp}.xlsx")
    final_excel_path = write_to_excel(extracted_data, excel_output_path, invoice_no, to, from_value, to_company, from_company, zip_paths_map, invoice_pdf_url, contract_pdf_url)

    print(f"\n{'='*60}")
    print(f"Processing complete!")
    print(f"{'='*60}")
    print(f"Deliverables folder: {deliverables_folder}")
    print(f"Excel file: {final_excel_path}")
    print(f"Total deliverables created: {len(zip_paths_map)}")
    print(f"{'='*60}\n")

    # Step 6: Upload to S3 if requested
    upload_results = None
    if upload_to_s3:
        upload_results = upload_zips_to_s3_and_update_excel(final_excel_path, s3_prefix, invoice_pdf_url, contract_pdf_url)

    # Step 7: Send data to webhook
    webhook_results = None
    webhook_results = send_to_webhook(final_excel_path, invoice_pdf_url, contract_pdf_url)

    return deliverables_folder, upload_results, webhook_results

# Function to get the file path from user input (command line)
def get_file_path():
    file_path = input("Enter the path of the Excel file: ")
    return file_path

# Function to ask if user wants to upload to S3
def ask_upload_to_s3():
    if not S3_AVAILABLE:
        return False
    response = input("Do you want to upload ZIP files to S3? (yes/no): ").strip().lower()
    return response in ['yes', 'y']

# Example: Start the file upload process
if __name__ == "__main__":
    import argparse

    # Parse command-line arguments
    parser = argparse.ArgumentParser(description='Process deliverables from Excel file')
    parser.add_argument('--excel', type=str, help='Path to Excel file')
    parser.add_argument('--invoice', type=str, help='Path to invoice PDF')
    parser.add_argument('--contract', type=str, help='Path to contract PDF')
    parser.add_argument('--s3', action='store_true', help='Upload to S3')
    parser.add_argument('--no-interactive', action='store_true', help='Run without user prompts')

    args = parser.parse_args()

    # Determine if running in interactive or non-interactive mode
    if args.no_interactive and args.excel:
        # Non-interactive mode (for Streamlit)
        uploaded_file_path = args.excel
        invoice_path = args.invoice
        contract_path = args.contract
        upload_to_s3 = args.s3

        # Store PDF paths for later use (can be accessed by deliverable generation)
        if invoice_path:
            print(f"Invoice PDF: {invoice_path}")
        if contract_path:
            print(f"Contract PDF: {contract_path}")

    else:
        # Interactive mode (original behavior)
        uploaded_file_path = get_file_path()  # Get the file path from the user
        upload_to_s3 = ask_upload_to_s3()
        invoice_path = None
        contract_path = None

    if uploaded_file_path:
        deliverables_folder, upload_results, webhook_results = process_file_and_generate_zip(
            uploaded_file_path,
            upload_to_s3=upload_to_s3,
            invoice_pdf_path=invoice_path,
            contract_pdf_path=contract_path,
            upload_to_sheets=False  # Removed Google Sheets integration
        )
        print(f"\n{'='*60}")
        print(f"All deliverables are in: {deliverables_folder}")
        if upload_results:
            print(f"S3 uploads: {upload_results['successful']}/{upload_results['total']} successful")
        if webhook_results and webhook_results.get("success"):
            print(f"Webhook: Data sent successfully (Status: {webhook_results.get('status_code')})")
        print(f"{'='*60}\n")

        # Return the deliverables folder path for Streamlit
        sys.exit(0)
    else:
        print("No file selected.")
        sys.exit(1)

