from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup
import time
import os
import pandas as pd

# Set up Chrome options
chrome_options = Options()
chrome_options.add_argument("--disable-gpu")
chrome_options.add_argument("--no-sandbox")
chrome_options.add_argument("--window-size=1920,1080")

# Auto-download PDF settings
download_dir = os.path.join(os.getcwd(), "downloads")
os.makedirs(download_dir, exist_ok=True)

prefs = {
    "download.default_directory": download_dir,
    "download.prompt_for_download": False,
    "download.directory_upgrade": True,
    "plugins.always_open_pdf_externally": True  # Auto-save PDFs
}
chrome_options.add_experimental_option("prefs", prefs)

# Initialize WebDriver
driver = webdriver.Chrome(options=chrome_options)
wait = WebDriverWait(driver, 15)

# Helper Functions
def click_js(link):
    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", link)
    time.sleep(0.5)
    driver.execute_script("arguments[0].click();", link)

def input_tms(tms, field_locator):
    field = wait.until(EC.presence_of_element_located(field_locator))
    field.clear()
    field.send_keys(tms)
    return field

def save_current_page(label, folder):
    """ Save current page as PDF using browser print """
    driver.execute_script('window.print();')
    time.sleep(2)  # Simulate print delay
    
    # Wait for download to complete
    pdf_files = []
    start_time = time.time()
    while len(pdf_files) == 0 and time.time() - start_time < 10:
        pdf_files = [f for f in os.listdir(download_dir) if f.endswith(".pdf")]
        time.sleep(1)
    
    if pdf_files:
        latest_file = max([os.path.join(download_dir, f) for f in pdf_files], key=os.path.getctime)
        filename = f"{label}.pdf"
        os.rename(latest_file, os.path.join(folder, filename))
        print(f"Saved: {filename}")
    else:
        print(f"⚠️ Failed to save: {label}")

# Charleston County Logic
def scrape_charleston(tms, base_folder):
    try:
        print(f"Scraping Charleston County for TMS: {tms}")
        driver.get("https://charlestoncounty.org/online-services.php") 

        # Step 1: Click "Pay Taxes & View Records"
        pay_link = wait.until(EC.element_to_be_clickable((By.PARTIAL_LINK_TEXT, "Pay Taxes & View Records")))
        click_js(pay_link)

        # Step 2: Click "Real Property Record Search"
        real_prop_link = wait.until(EC.element_to_be_clickable((By.LINK_TEXT, "Real Property Record Search")))
        click_js(real_prop_link)

        # Step 3: Input TMS without dashes
        pin_input = input_tms(tms.replace('-', ''), (By.ID, "txtPIN"))
        driver.find_element(By.ID, "btnSearch").click()

        # Step 4: Click View Details
        view_details = wait.until(EC.element_to_be_clickable((By.LINK_TEXT, "View Details")))
        click_js(view_details)

        # Step 5: Save Property Card
        save_current_page("Property Card", base_folder)

        # Step 6: Get Book/Page numbers
        soup = BeautifulSoup(driver.page_source, "html.parser")
        trans_table = soup.find("table", id="grdTransactions")
        deed_links = []
        
        if trans_table:
            rows = trans_table.find_all("tr")[1:]  # Skip header
            for row in rows:
                cols = row.find_all("td")
                if len(cols) >= 2:
                    book_page = cols[1].text.strip()
                    
                    # Only keep valid books starting with letter + A280+
                    if book_page and book_page[0].isalpha():
                        num_part = int(book_page[1:])
                        if num_part >= 280:
                            deed_links.append(book_page)
                    elif book_page and book_page[0].isdigit():
                        # Keep numeric books too (some newer ones might be numeric)
                        deed_links.append(book_page)

        # Step 7: Go to Tax Info
        tax_info = wait.until(EC.element_to_be_clickable((By.LINK_TEXT, "Tax Info")))
        click_js(tax_info)
        save_current_page("Tax Info", base_folder)

        # Step 8: Go to Register of Deeds
        driver.get("https://docviewer.charlestoncounty.org/ROD/BookSearch.aspx") 
        
        for bp in deed_links:
            book, page = bp[:bp.index(" ")], bp[bp.index(" ")+1:]
            page = page.zfill(3)  # Add leading zeros
            
            book_input = wait.until(EC.presence_of_element_located((By.NAME, "book[booknum]")))
            book_input.clear()
            book_input.send_keys(book)
            
            page_input = driver.find_element(By.NAME, "book[pagenum]")
            page_input.clear()
            page_input.send_keys(page)
            
            driver.find_element(By.ID, "disclaimerCheck").click()
            driver.find_element(By.XPATH, '//input[@value="Search"]').click()
            
            result_link = wait.until(EC.element_to_be_clickable((By.PARTIAL_LINK_TEXT, "View Document")))
            result_link.click()
            
            driver.switch_to.window(driver.window_handles[-1])
            save_current_page(f"DB {book} {page}", base_folder)
            driver.close()
            driver.switch_to.window(driver.window_handles[0])
            
            # Go back to search
            driver.get("https://docviewer.charlestoncounty.org/ROD/BookSearch.aspx") 

    except Exception as e:
        print(f"Error scraping Charleston TMS {tms}: {e}")

# Berkeley County Logic
def scrape_berkeley(tms, base_folder):
    try:
        print(f"Scraping Berkeley County for TMS: {tms}")
        driver.get("https://berkeleycountysc.gov/propcards/property_card.php") 
        
        # Step 1: Enter TMS
        tms_input = input_tms(tms.replace('-', ''), (By.NAME, "tms"))
        driver.find_element(By.XPATH, '//input[@value="Retrieve Property Card"]').click()
        
        # Step 2: Save Property Card
        save_current_page("Property Card", base_folder)
        
        # Step 3: Parse conveyances
        soup = BeautifulSoup(driver.page_source, "html.parser")
        conveyance_rows = soup.select("#previousOwnerHistory tr")
        deed_list = []
        
        for row in conveyance_rows[1:]:
            cols = row.find_all("td")
            if len(cols) >= 2:
                bp = cols[1].text.strip()
                if bp:
                    deed_list.append(bp)
        
        # Step 4: Go to Tax Info
        driver.get("https://taxsearch.berkeleycountysc.gov/") 
        
        tms_input = input_tms(tms.replace('-', ''), (By.NAME, "parcelid"))
        driver.find_element(By.XPATH, '//button[@type="submit"]').click()
        
        view_link = wait.until(EC.element_to_be_clickable((By.LINK_TEXT, "View")))
        click_js(view_link)
        
        bill_tab = wait.until(EC.element_to_be_clickable((By.LINK_TEXT, "View & Print Bill")))
        click_js(bill_tab)
        save_current_page("Tax Bill", base_folder)
        
        try:
            receipt_tab = wait.until(EC.element_to_be_clickable((By.LINK_TEXT, "View & Print Receipt")))
            click_js(receipt_tab)
            save_current_page("Tax Receipt", base_folder)
        except:
            print("No tax receipt available.")
        
        # Step 5: Go to Deeds site
        driver.get("https://search.berkeleydeeds.com/NameSearch.php?Accept=Accept")
        
        for bp in deed_list:
            book, page = bp.split()
            page = page.zfill(3)
            
            # Step 6: Check date filed to determine book type 
            # Default is RECORD BOOK, but switch to OLD REAL PROPERTY for pre-2015 entries
            book_type_dropdown = wait.until(EC.element_to_be_clickable((By.NAME, "booktype")))
            book_type_dropdown.click()
            
            # For demo purposes, we'll assume all are OLD REAL PROPERTY
            book_type_dropdown.find_element(By.XPATH, '//option[text()="OLD REAL PROPERTY"]').click()
            
            book_input = wait.until(EC.presence_of_element_located((By.NAME, "book[booknum]")))
            book_input.clear()
            book_input.send_keys(book)
            
            page_input = driver.find_element(By.NAME, "book[pagenum]")
            page_input.clear()
            page_input.send_keys(page)
            
            driver.find_element(By.XPATH, '//input[@value="Search"]').click()
            
            result_link = wait.until(EC.element_to_be_clickable((By.PARTIAL_LINK_TEXT, "Document Image")))
            result_link.click()
            
            driver.switch_to.window(driver.window_handles[-1])
            save_current_page(f"DB {book} {page}", base_folder)
            driver.close()
            driver.switch_to.window(driver.window_handles[0])
            
            # Go back to search
            driver.get("https://search.berkeleydeeds.com/NameSearch.php?Accept=Accept")

    except Exception as e:
        print(f"Error scraping Berkeley TMS {tms}: {e}")

# Main Execution 
if __name__ == "__main__":
    df = pd.read_excel("parcels.xlsx", engine="openpyxl")
    output_dir = "property_records"
    os.makedirs(output_dir, exist_ok=True)

    for _, row in df.iterrows():
        tms = str(row["TMS"]).strip()
        county = row["County"].strip().lower()

        folder = os.path.join(output_dir, tms)
        os.makedirs(folder, exist_ok=True)

        if county == "charleston":
            scrape_charleston(tms, folder)
        elif county == "berkeley":
            scrape_berkeley(tms, folder)
        else:
            print(f"Unknown county: {county} for TMS: {tms}")

    driver.quit()
    print("✅ Completed scraping all properties.")