### Test the Selenium Grid ####
#
from selenium import webdriver
from selenium.webdriver.common.desired_capabilities import DesiredCapabilities

def test_google():
    # Connect to the Selenium Grid Hub
    grid_url = "http://localhost:4444/wd/hub"
    
    # Set up desired capabilities for Chrome
    chrome_options = webdriver.ChromeOptions()
    
    # Create a new Chrome session
    driver = webdriver.Remote(
        command_executor=grid_url,
        options=chrome_options
    )
    
    # Open a website
    driver.get("https://www.google.com")
    
    # Check the title
    assert "Google" in driver.title
    
    # Print the title to the console
    print(driver.title)
    
    # Close the browser
    driver.quit()

if __name__ == "__main__":
    test_google()

