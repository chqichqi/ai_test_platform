#!/usr/bin/env python3
"""Simple Playwright test to verify installation"""
import asyncio
from playwright.async_api import async_playwright

async def test_playwright():
    """Test Playwright can launch browser"""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto("http://localhost:3004")
        title = await page.title()
        print(f"Page title: {title}")
        await browser.close()
        return title

if __name__ == "__main__":
    result = asyncio.run(test_playwright())
    print(f"Playwright test completed: {result}")