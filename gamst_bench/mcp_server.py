"""Private stdio MCP surface. Use SSH stdio to run this process on GCE."""
import argparse
from typing import Any
from functools import wraps
from mcp.server.mcpserver.exceptions import ToolError
from mcp.server import MCPServer
from .contracts import read,require
from .mcp_jobs import Jobs,catalog,ROOT


def errors(fn):
    @wraps(fn)
    def wrapped(*args,**kwargs):
        try:return fn(*args,**kwargs)
        except (ValueError,FileNotFoundError) as e:raise ToolError(str(e)) from e
    return wrapped


def create_server(jobs):
    server=MCPServer('Gamst Bench',version='0.3.0',instructions='Published references are not measurements. Execute registered profiles only on GCE. Native output needs independent review; no automatic official submission.')
    @server.tool(structured_output=True)
    @errors
    def list_benchmarks() -> dict[str, Any]:
        """List the three core executable families (FastBench, OmniPro, StreamArena) plus reference-only catalog entries."""
        return {'benchmarks':catalog()}
    @server.tool(structured_output=True)
    @errors
    def get_benchmark(benchmark_id:str) -> dict[str, Any]:
        """Read capability, data requirements, native recipes, metrics and source revisions."""
        item=next((b for b in catalog() if b['id']==benchmark_id),None)
        require(item is not None,'unknown benchmark')
        return {'benchmark':item,'recipes':[r for r in read(ROOT/'mcp/recipes.json') if r['benchmark']==benchmark_id]}
    @server.tool(structured_output=True)
    @errors
    def detect_environment() -> dict[str, Any]:
        """Detect host OS, architecture, Python, NVIDIA and GCP CLI availability without side effects."""
        return jobs.environment('local')
    @server.tool(structured_output=True)
    @errors
    def plan_environment(target:str='local',project_id:str='',region:str='us-central1') -> dict[str, Any]:
        """Generate reviewable OS-aware MCP/GCP setup commands; never executes them or downloads data/models."""
        return jobs.environment(target,False,project_id or None,region)
    @server.tool(structured_output=True)
    @errors
    def setup_environment(target:str='local',install:bool=False,project_id:str='',region:str='us-central1') -> dict[str, Any]:
        """Install only local MCP dependencies when install=true; GCP always returns commands for explicit operator review."""
        return jobs.prepare_environment(target,project_id or None,region) if install else jobs.environment(target,False,project_id or None,region)
    @server.tool(structured_output=True)
    @errors
    def list_profiles() -> dict[str, Any]:
        """List operator-installed execution profiles and unresolved setup requirements."""
        return {'profiles':jobs.profiles_info()}
    @server.tool(structured_output=True)
    @errors
    def plan_evaluation(profile_id:str) -> dict[str, Any]:
        """Validate a registered frozen profile without inference, data downloads or GCE access."""
        return jobs.plan(profile_id)
    @server.tool(structured_output=True)
    @errors
    def start_evaluation(profile_id:str,profile_sha256:str) -> dict[str, Any]:
        """Start a registered evaluation on the matching GCE VM; returns run ID immediately."""
        return jobs.start(profile_id,profile_sha256)
    @server.tool(structured_output=True)
    @errors
    def plan_dataset(profile_id:str) -> dict[str, Any]:
        """Plan a pinned GCP dataset download before the dataset file manifest exists."""
        return jobs.plan(profile_id,operation='dataset')
    @server.tool(structured_output=True)
    @errors
    def prepare_dataset(profile_id:str,profile_sha256:str) -> dict[str, Any]:
        """Download the catalog dataset's pinned revision on GCE only, then hash files. Requires a reviewed profile and a new data directory."""
        return jobs.start(profile_id,profile_sha256,operation='dataset')
    @server.tool(structured_output=True)
    @errors
    def list_runs() -> dict[str, Any]:
        """List up to 100 persistent run records in this server's private run root."""
        return jobs.list_runs()
    @server.tool(structured_output=True)
    @errors
    def get_run(run_id:str) -> dict[str, Any]:
        """Read persistent run status. Execution finished is not a validated score."""
        return jobs.status(run_id)
    @server.tool(structured_output=True)
    @errors
    def cancel_run(run_id:str) -> dict[str, Any]:
        """Request cancellation of this run's subprocesses; does not stop VM/model servers."""
        return jobs.cancel(run_id)
    @server.tool(structured_output=True)
    @errors
    def list_artifacts(run_id:str) -> dict[str, Any]:
        """List run-scoped native outputs, resource samples and provenance artifacts."""
        return jobs.artifacts(run_id)
    @server.tool(structured_output=True)
    @errors
    def read_artifact(run_id:str,path:str) -> dict[str, Any]:
        """Read up to 32 KiB of a run-scoped text artifact; private logs may contain dataset text."""
        return jobs.read_artifact(run_id,path)
    return server


def main():
    p=argparse.ArgumentParser();p.add_argument('--config');a=p.parse_args()
    create_server(Jobs(read(a.config) if a.config else None)).run(transport='stdio')

if __name__=='__main__':main()
