
import pytest
import os
import asyncio
from unittest import mock

# Ensure imports work by patching before import if needed.
# We need to make sure 'app.langgraph_v2.utils.checkpointer' is imported.

def test_checkpointer_tenant_prefix():
    async def _test():
        env_vars = {
            "REDIS_URL": "redis://localhost:6379/0",
            "LANGGRAPH_V2_CHECKPOINTER_PREFIX": "lg:cp"
        }
        
        with mock.patch.dict(os.environ, env_vars):
            with mock.patch("app.langgraph_v2.utils.checkpointer.ConnectionPool") as MockPool:
                     MockPool.from_url.return_value = mock.Mock()
                     
                     with mock.patch("app.langgraph_v2.utils.checkpointer._construct_async_redis_saver") as mock_construct:
                        
                        # Mock AsyncRedisSaver class
                        MockSaverClass = mock.Mock()
                        # IMPORTANT: Ensure the instance returned has an awaitable asetup
                        MockSaverInstance = mock.Mock()
                        MockSaverInstance.asetup = mock.AsyncMock() # Make asetup awaitable
                        MockSaverClass.return_value = MockSaverInstance
                        
                        # mock_construct returns this instance usually?
                        # No, checkpointer logic:
                        # saver = _construct_async_redis_saver(...) 
                        # await saver.asetup()
                        
                        # So mock_construct MUST return an object with awaitable asetup
                        mock_construct.return_value = MockSaverInstance

                        with mock.patch("app.langgraph_v2.utils.checkpointer.AsyncRedisSaver", new=MockSaverClass):
                            with mock.patch("app.langgraph_v2.utils.checkpointer.Redis"):
                            
                                from app.langgraph_v2.utils.checkpointer import make_v2_checkpointer_async
                                await make_v2_checkpointer_async(tenant_id="tenantA", namespace="ns1")
                                
                                if mock_construct.called:
                                    found = False
                                    for k, v in mock_construct.call_args[1].items():
                                         if isinstance(v, str) and "tenant:tenantA" in v:
                                             found = True
                                    for arg in mock_construct.call_args[0]:
                                         if isinstance(arg, str) and "tenant:tenantA" in arg:
                                             found = True
                                    assert found, "Tenant prefix not passed to _construct_async_redis_saver"
                                else:
                                    pytest.fail("_construct_async_redis_saver was not called")

    asyncio.run(_test())

def test_checkpointer_tenant_prefix_integration():
    async def _test():
        env_vars = {
            "REDIS_URL": "redis://localhost:6379/0",
            "LANGGRAPH_V2_CHECKPOINTER_PREFIX": "lg:v2"
        }
        with mock.patch.dict(os.environ, env_vars):
            with mock.patch("app.langgraph_v2.utils.checkpointer.ConnectionPool") as MockPool:
                MockPool.from_url.return_value = mock.Mock()
                with mock.patch("app.langgraph_v2.utils.checkpointer.Redis"):
                    
                    # Mock AsyncRedisSaver class
                    MockSaverClass = mock.Mock()
                    MockSaverInstance = mock.Mock()
                    MockSaverInstance.asetup = mock.AsyncMock()
                    MockSaverClass.return_value = MockSaverInstance
                    
                    with mock.patch("app.langgraph_v2.utils.checkpointer.AsyncRedisSaver", new=MockSaverClass) as MockSaverPatch:
                         
                         from app.langgraph_v2.utils.checkpointer import make_v2_checkpointer_async
                         
                         await make_v2_checkpointer_async(tenant_id="tenantA")
                         
                         found = False
                         # MockSaverPatch is the class mock. It was called to instantiate.
                         # Wait, _construct calls AsyncRedisSaver()
                         
                         if MockSaverPatch.call_args:
                            for k, v in MockSaverPatch.call_args.kwargs.items():
                                if isinstance(v, str) and "tenant:tenantA" in v:
                                    found = True
                            if not found:
                                 for arg in MockSaverPatch.call_args.args:
                                    if isinstance(arg, str) and "tenant:tenantA" in arg:
                                        found = True
                         else:
                            # It implies _construct_async_redis_saver logic called it.
                            # We didn't patch _construct logic here (in integration test), so real logic runs.
                            # So MockSaverPatch() should be called.
                            pass
                            
                         # Robust check: Check MockSaverPatch calls
                         if not found and MockSaverPatch.call_count > 0:
                             for call in MockSaverPatch.call_args_list:
                                 for k, v in call.kwargs.items():
                                     if isinstance(v, str) and "tenant:tenantA" in v:
                                         found = True
                                 for arg in call.args:
                                     if isinstance(arg, str) and "tenant:tenantA" in arg:
                                         found = True
                         
                         if MockSaverPatch.call_count == 0:
                             pytest.fail("AsyncRedisSaver was not instantiated")

                         assert found, "Tenant ID not found in AsyncRedisSaver init arguments"
    asyncio.run(_test())
