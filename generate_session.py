import asyncio
from pyrogram import Client

async def main():
    print("==================================================")
    print("      Pyrogram Session String Generator           ")
    print("==================================================")
    print("You will need your API ID and API HASH from https://my.telegram.org")
    
    api_id = input("\nEnter API ID: ").strip()
    if not api_id.isdigit():
        print("❌ API ID must be a number!")
        return
        
    api_hash = input("Enter API HASH: ").strip()
    if not api_hash:
        print("❌ API HASH cannot be empty!")
        return

    print("\nStarting Pyrogram client setup...")
    print("It will prompt for your phone number and login code.")
    
    # We use an in-memory session to generate the string session
    async with Client(":memory:", api_id=int(api_id), api_hash=api_hash) as app:
        session_string = await app.export_session_string()
        print("\n✅ LOGIN SUCCESSFUL!")
        print("==================================================")
        print("Your SESSION_STRING is:")
        print("==================================================")
        print(session_string)
        print("==================================================")
        print("Copy the entire string above and paste it into your .env file.")

if __name__ == "__main__":
    asyncio.run(main())
