"""
Clear all incidents from MongoDB
"""
import asyncio
import sys
import os

# Add parent directory to path to import app modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.mongodb import connect_to_mongo, get_database, close_mongo_connection

async def clear_all_incidents():
    """Delete all incidents and related data from MongoDB"""
    # Connect to MongoDB
    await connect_to_mongo()
    
    db = get_database()
    
    if db is None:
        print("❌ Database connection failed")
        return
    
    print("🗑️  Clearing all incidents from MongoDB...")
    
    # Delete incidents
    incidents_result = await db.incidents.delete_many({})
    print(f"✅ Deleted {incidents_result.deleted_count} incidents")
    
    # Delete incident patterns
    patterns_result = await db.incident_patterns.delete_many({})
    print(f"✅ Deleted {patterns_result.deleted_count} incident patterns")
    
    # Delete agent sessions
    sessions_result = await db.agent_sessions.delete_many({})
    print(f"✅ Deleted {sessions_result.deleted_count} agent sessions")
    
    # Delete workflow executions
    executions_result = await db.workflow_executions.delete_many({})
    print(f"✅ Deleted {executions_result.deleted_count} workflow executions")
    
    print("\n✨ All incidents cleared successfully!")
    print(f"📊 Total records deleted: {incidents_result.deleted_count + patterns_result.deleted_count + sessions_result.deleted_count + executions_result.deleted_count}")
    
    # Close connection
    await close_mongo_connection()

if __name__ == "__main__":
    asyncio.run(clear_all_incidents())
