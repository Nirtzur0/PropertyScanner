<instruction>You are an expert software engineer. You are working on a WIP branch. Please run `git status` and `git diff` to understand the changes and the current state of the code. Analyze the workspace context and complete the mission brief.</instruction>
<workspace_context>
</workspace_context>
<mission_brief>
Analyzed the workspace state and identified a Pydantic validation error in `tests/test_cognitive.py` due to a mismatch between `config/sources.yaml` structure and `SourcesConfig` schema. 
Fixed the issue by nesting the sources list under a `sources` key in `config/sources.yaml`. 
Verified the fix by running the affected tests.
</mission_brief>