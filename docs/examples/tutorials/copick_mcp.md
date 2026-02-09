## copick :fontawesome-solid-heart: [Model Context Protocol](https://modelcontextprotocol.io)

The Copick MCP Server enables Claude AI (Claude Desktop and Claude Code) to interact with copick projects. It provides
two sets of tools:

1. **Data Exploration Tools** - Browse and query copick project contents (read-only)
2. **CLI Introspection Tools** - Discover and validate copick CLI commands for building processing pipelines

### Step 1: Install copick-mcp

Install the copick-mcp package:

```bash
cd copick-mcp
pip install -e .
```

### Step 2: Register with Claude

The MCP server can be registered with Claude Desktop or Claude Code using the `copick setup mcp` command.

#### Claude Desktop

```bash
# Basic setup (default settings)
copick setup mcp

# Setup with custom server name
copick setup mcp --server-name "my-copick-server"

# Setup with default config path (optional - can be provided per-request)
copick setup mcp --config-path "/path/to/default/config.json"
```

After setup:

1. Restart Claude Desktop completely
2. The Copick MCP tools should now be available
3. The server starts automatically when Claude Desktop connects

#### Claude Code

```bash
# Global setup (available in all Claude Code sessions)
copick setup mcp --target code-global

# Project-specific setup (creates .mcp.json in current directory)
copick setup mcp --target code-project

# Project-specific setup for a different directory
copick setup mcp --target code-project --project-path /path/to/project
```

**Target options:**

- `desktop` (default) - Claude Desktop application
- `code-global` - Claude Code global config (`~/.claude.json`)
- `code-project` - Claude Code project-specific config (`.mcp.json` in project root)

#### Check Status

```bash
# Check status for Claude Desktop
copick setup mcp-status

# Check status for Claude Code
copick setup mcp-status --target code-global
copick setup mcp-status --target code-project
```

### Step 3: Manual Configuration (Optional)

If you prefer manual setup, add the following configuration to the appropriate file:

**Configuration file locations:**

| Platform | Claude Desktop | Claude Code Global | Claude Code Project |
|----------|----------------|-------------------|---------------------|
| macOS | `~/Library/Application Support/Claude/claude_desktop_config.json` | `~/.claude.json` | `.mcp.json` |
| Windows | `%APPDATA%/Claude/claude_desktop_config.json` | `~/.claude.json` | `.mcp.json` |
| Linux | `~/.config/Claude/claude_desktop_config.json` | `~/.claude.json` | `.mcp.json` |

**Configuration format:**

```json
{
  "mcpServers": {
    "copick-mcp": {
      "command": "python",
      "args": ["-m", "copick_mcp.main"],
      "env": {}
    }
  }
}
```

### Step 4: Available Tools

#### Data Exploration Tools (Read-Only)

All data exploration tools require a `config_path` parameter pointing to your copick configuration file.

| Tool | Description |
|------|-------------|
| `list_runs` | List all runs in a copick project |
| `get_run_details` | Get comprehensive run information (voxel spacings, picks, meshes, segmentations) |
| `list_objects` | List pickable objects with properties (name, type, label, color, radius) |
| `list_picks` | List picks with optional filtering by object, user, session |
| `list_meshes` | List meshes with filtering options |
| `list_segmentations` | List segmentations with various filter parameters |
| `list_tomograms` | List tomograms for specific voxel spacings |
| `list_voxel_spacings` | List all voxel spacings in a run |
| `get_project_info` | Get project metadata and statistics |
| `get_json_config` | Get raw JSON configuration |

#### CLI Introspection Tools

These tools help Claude discover and validate copick CLI commands for building processing pipelines.

| Tool | Description |
|------|-------------|
| `list_copick_cli_commands` | List all available copick CLI commands hierarchically organized by group |
| `get_copick_cli_command_info` | Get detailed information about a specific command including parameters, types, and defaults |
| `validate_copick_cli_command` | Validate copick CLI command syntax using Click's native parsing |

### Step 5: Usage Examples

#### Data Exploration Workflow

```
User: "Show me all runs in my copick project at /data/my_project/config.json"

Claude uses: list_runs(config_path="/data/my_project/config.json")

User: "What picks are available for run TS_001?"

Claude uses: list_picks(config_path="/data/my_project/config.json", run_name="TS_001")

User: "Show me only the ribosome picks from user 'annotator1'"

Claude uses: list_picks(
    config_path="/data/my_project/config.json",
    run_name="TS_001",
    object_name="ribosome",
    user_id="annotator1"
)
```

#### CLI Discovery Workflow

```
User: "I want to convert picks to a segmentation. What copick command can do that?"

Claude uses: list_copick_cli_commands()
# Discovers convert.picks2seg command

Claude uses: get_copick_cli_command_info(command_path="convert.picks2seg")
# Gets full documentation and parameters

Claude explains:
"The picks2seg command converts picks to segmentation by painting spheres at pick locations.
It requires:
- --config: Path to copick config
- --input: Picks URI (format: object_name:user_id/session_id)
- --output: Segmentation URI (format: name:user_id/session_id@voxel_spacing)
- --radius: Sphere radius in angstroms (default: 10.0)"
```

#### Pipeline Building Workflow

```
User: "I want to build a pipeline that:
1. Converts ribosome picks to meshes
2. Computes the convex hull of those meshes
3. Converts the hulls to segmentations"

Claude uses: list_copick_cli_commands()
# Discovers relevant commands in convert and process groups

Claude uses: get_copick_cli_command_info(command_path="convert.picks2mesh")
Claude uses: get_copick_cli_command_info(command_path="process.hull")
Claude uses: get_copick_cli_command_info(command_path="convert.mesh2seg")
# Gets documentation for each command

Claude suggests the pipeline:
"Here's a three-step pipeline for your workflow:

Step 1: Convert picks to meshes
copick convert picks2mesh --config /path/to/config.json \
    --input 'ribosome:user1/manual-001' \
    --output 'ribosome:pipeline/step1-meshes' \
    --method convex_hull

Step 2: Compute convex hull
copick process hull --config /path/to/config.json \
    --input-mesh 'ribosome:pipeline/step1-meshes' \
    --output-mesh 'ribosome:pipeline/step2-hulls'

Step 3: Convert meshes to segmentation
copick convert mesh2seg --config /path/to/config.json \
    --input 'ribosome:pipeline/step2-hulls' \
    --output 'ribosome:pipeline/final-seg@10.0'"
```

### Step 6: Management Commands

```bash
# Remove MCP server configuration (Claude Desktop)
copick setup mcp-remove --server-name "copick-mcp"

# Remove from Claude Code
copick setup mcp-remove --server-name "copick-mcp" --target code-global
copick setup mcp-remove --server-name "copick-mcp" --target code-project

# Force removal without confirmation
copick setup mcp-remove --server-name "copick-mcp" --force
```

### Troubleshooting

| Issue | Solution |
|-------|----------|
| "MCP server not found" | Ensure you've restarted Claude Desktop completely after configuration |
| "Python module not found" | Verify the package is installed and the Python path is correct in the config |
| "Permission denied" | Check that the Claude config directory is writable |
| "Invalid JSON" | Use `copick setup mcp-status` to validate your configuration |
| "Command not found" during CLI introspection | Ensure copick and all plugin packages (copick-torch, copick-utils) are installed |
| "setup command not found" | Make sure copick-mcp is installed (`pip install -e .` from the copick-mcp directory) |

### Links

- [Model Context Protocol](https://modelcontextprotocol.io)
- [FastMCP](https://github.com/jlowin/fastmcp)
- [copick-mcp Repository](https://github.com/copick/copick-mcp)
