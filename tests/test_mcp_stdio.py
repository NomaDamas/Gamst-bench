"""Real MCP client/server handshake; never starts an inference job."""
import importlib.util
import sys
import unittest
from pathlib import Path

@unittest.skipUnless(importlib.util.find_spec('mcp'),'install requirements-mcp.txt for protocol tests')
class StdioTests(unittest.IsolatedAsyncioTestCase):
 async def test_real_stdio_tools_and_catalog(self):
  from mcp import Client,StdioServerParameters
  params=StdioServerParameters(command=sys.executable,args=['-m','gamst_bench.mcp_server'],cwd=str(Path(__file__).resolve().parents[1]))
  async with Client(params) as client:
   listed=await client.list_tools()
   names={t.name for t in listed.tools}
   self.assertTrue({'list_benchmarks','detect_environment','plan_environment','setup_environment','plan_evaluation','start_evaluation','list_runs','prepare_dataset','cancel_run','read_artifact'}<=names)
   result=await client.call_tool('list_benchmarks',{})
   self.assertFalse(result.is_error)
   supported=[b for b in result.structured_content['benchmarks'] if b['mcp_support']=='registered native runner']
   self.assertEqual({b['id'] for b in supported},{'fastbench','omnipro','streamarena'})
   env=await client.call_tool('detect_environment',{})
   self.assertFalse(env.is_error);self.assertFalse(env.structured_content['execution_allowed'])
   details=await client.call_tool('get_benchmark',{'benchmark_id':'fastbench'})
   self.assertFalse(details.is_error);self.assertTrue(details.structured_content['recipes'])
   profiles=await client.call_tool('list_profiles',{})
   self.assertEqual(profiles.structured_content['profiles'],[])
   denied=await client.call_tool('start_evaluation',{'profile_id':'invented','profile_sha256':'a'*64})
   self.assertTrue(denied.is_error)

if __name__=='__main__':unittest.main()
