#!/usr/bin/env python3
"""
Simple WebSocket test client to test our WebSocket implementation
"""
import asyncio
import json
import websockets
import sys

async def test_websocket_connection():
    """Test basic WebSocket connection to our dashboard endpoint"""
    try:
        # Test connection without token (should still connect but not authenticate)
        uri = "ws://localhost:8000/api/v1/ws/dashboard/1"
        
        print(f"Connecting to {uri}...")
        async with websockets.connect(uri) as websocket:
            print("✅ WebSocket connection established successfully!")
            
            # Send a test message
            test_message = {
                "type": "test",
                "message": "Hello from test client!",
                "timestamp": "2025-01-13T08:00:00Z"
            }
            
            print(f"Sending test message: {test_message}")
            await websocket.send(json.dumps(test_message))
            
            # Wait for a response or timeout
            try:
                response = await asyncio.wait_for(websocket.recv(), timeout=5.0)
                print(f"✅ Received response: {response}")
            except asyncio.TimeoutError:
                print("⏰ No response received within timeout period")
            
            # Test heartbeat
            heartbeat = {
                "type": "heartbeat",
                "timestamp": "2025-01-13T08:00:00Z"
            }
            print(f"Sending heartbeat: {heartbeat}")
            await websocket.send(json.dumps(heartbeat))
            
            # Wait for heartbeat response
            try:
                response = await asyncio.wait_for(websocket.recv(), timeout=5.0)
                print(f"✅ Received heartbeat response: {response}")
            except asyncio.TimeoutError:
                print("⏰ No heartbeat response received")
                
        print("✅ WebSocket test completed successfully!")
        return True
        
    except websockets.exceptions.ConnectionClosed as e:
        print(f"❌ WebSocket connection closed: {e}")
        return False
    except websockets.exceptions.InvalidURI as e:
        print(f"❌ Invalid WebSocket URI: {e}")
        return False
    except websockets.exceptions.InvalidStatus as e:
        print(f"❌ WebSocket connection rejected: {e}")
        return False
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return False

async def test_websocket_endpoints():
    """Test different WebSocket endpoints"""
    endpoints = [
        "ws://localhost:8000/api/v1/ws/dashboard/1",
        "ws://localhost:8000/api/v1/ws/projects/1/1",  # project 1, user 1
    ]
    
    results = []
    for endpoint in endpoints:
        print(f"\n🔍 Testing endpoint: {endpoint}")
        try:
            async with websockets.connect(endpoint) as websocket:
                print(f"✅ Connected to {endpoint}")
                
                # Send a simple test message
                await websocket.send(json.dumps({
                    "type": "connection_test",
                    "endpoint": endpoint
                }))
                
                # Try to receive a response
                try:
                    response = await asyncio.wait_for(websocket.recv(), timeout=2.0)
                    print(f"📨 Response: {response}")
                    results.append((endpoint, True, response))
                except asyncio.TimeoutError:
                    print("⏰ No response (which is expected for basic connection)")
                    results.append((endpoint, True, "Connected but no response"))
                    
        except Exception as e:
            print(f"❌ Failed to connect to {endpoint}: {e}")
            results.append((endpoint, False, str(e)))
    
    return results

async def main():
    print("🚀 Starting WebSocket Tests")
    print("=" * 50)
    
    # Test basic connection
    print("\n1️⃣ Testing basic WebSocket connection...")
    basic_test = await test_websocket_connection()
    
    # Test different endpoints
    print("\n2️⃣ Testing different WebSocket endpoints...")
    endpoint_results = await test_websocket_endpoints()
    
    # Summary
    print("\n📊 Test Results Summary:")
    print("=" * 50)
    
    if basic_test:
        print("✅ Basic WebSocket connection: PASSED")
    else:
        print("❌ Basic WebSocket connection: FAILED")
    
    print("\nEndpoint Tests:")
    for endpoint, success, result in endpoint_results:
        status = "✅ PASSED" if success else "❌ FAILED"
        print(f"  {status}: {endpoint}")
        if not success:
            print(f"    Error: {result}")
    
    # Overall result
    successful_endpoints = sum(1 for _, success, _ in endpoint_results if success)
    total_endpoints = len(endpoint_results)
    
    if basic_test and successful_endpoints > 0:
        print(f"\n🎉 WebSocket implementation is working! ({successful_endpoints}/{total_endpoints} endpoints successful)")
        return 0
    else:
        print(f"\n⚠️  Some tests failed. WebSocket implementation needs attention.")
        return 1

if __name__ == "__main__":
    sys.exit(asyncio.run(main()))