#!/usr/bin/env python3
"""Explore the UI with Playwright to check for functional tests and test WEB UI conversion"""
import asyncio
import json
from playwright.async_api import async_playwright

async def explore_ui():
    """Explore the UI to understand current state"""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)  # Show browser for debugging
        context = await browser.new_context()
        page = await context.new_page()
        
        # Go to frontend
        await page.goto("http://localhost:3004")
        print("Opened frontend")
        
        # Check if already logged in
        if await page.locator('text=Login').count() > 0:
            print("Need to login")
            await page.fill('input[name="username"]', 'admin')
            await page.fill('input[name="password"]', 'admin123')
            await page.click('button[type="submit"]')
            await page.wait_for_timeout(2000)
        
        # Check current page
        title = await page.title()
        print(f"Page title: {title}")
        
        # Check for functional tests menu item
        if await page.locator('text=功能测试').count() > 0:
            print("Functional tests menu found")
            await page.click('text=功能测试')
            await page.wait_for_timeout(1000)
            
            # Check if there are any functional tests listed
            test_items = await page.locator('.test-item, [data-testid*="test"]').count()
            print(f"Functional test items found: {test_items}")
            
            if test_items == 0:
                print("No functional tests found. Creating a sample functional test...")
                # Look for create button
                if await page.locator('text=新建, button:has-text("新建")').count() > 0:
                    await page.click('text=新建, button:has-text("新建")')
                    await page.wait_for_timeout(1000)
                    
                    # Fill sample test data
                    await page.fill('input[name="name"], [placeholder*="名称"]', 'Sample Functional Test for WEB UI Conversion')
                    await page.fill('textarea[name="description"], [placeholder*="描述"]', 'This is a sample functional test to test WEB UI conversion')
                    
                    # Look for test steps input
                    if await page.locator('textarea[name="test_steps"], [placeholder*="步骤"]').count() > 0:
                        test_steps = [
                            {"step": 1, "action": "打开页面", "target": "/", "value": "", "expected": "页面加载成功"},
                            {"step": 2, "action": "点击登录按钮", "target": "button.login-btn", "value": "", "expected": "显示登录表单"},
                            {"step": 3, "action": "输入用户名", "target": "input[name='username']", "value": "admin", "expected": "用户名输入框显示值"},
                            {"step": 4, "action": "输入密码", "target": "input[name='password']", "value": "admin123", "expected": "密码输入框显示值"},
                            {"step": 5, "action": "点击提交", "target": "button[type='submit']", "value": "", "expected": "登录成功，跳转到首页"}
                        ]
                        await page.fill('textarea[name="test_steps"], [placeholder*="步骤"]', json.dumps(test_steps, ensure_ascii=False))
                    
                    # Save the test
                    await page.click('button:has-text("保存"), button[type="submit"]')
                    await page.wait_for_timeout(2000)
                    print("Sample functional test created")
        else:
            print("Functional tests menu not found")
        
        # Check for WEB UI tests menu
        if await page.locator('text=WEB UI测试').count() > 0:
            print("WEB UI tests menu found")
            await page.click('text=WEB UI测试')
            await page.wait_for_timeout(1000)
            
            # Check if there's a conversion button
            if await page.locator('text=从功能测试转换').count() > 0:
                print("WEB UI conversion button found")
                # Take screenshot
                await page.screenshot(path='web_ui_page.png')
                print("Screenshot saved to web_ui_page.png")
        
        # Take final screenshot
        await page.screenshot(path='final_page.png')
        print("Final screenshot saved to final_page.png")
        
        # Get cookies/token for API testing
        cookies = await context.cookies()
        print(f"Cookies: {len(cookies)}")
        
        await browser.close()

if __name__ == "__main__":
    asyncio.run(explore_ui())