"""Verify the agent account's Pi web tools without credentials or model calls."""

import json


def test_pi_web_access_is_current_and_owned_by_the_agent(host, agents_user, agents_home):
    package = host.file(f"{agents_home}/.pi/agent/npm/node_modules/pi-web-access/package.json")
    assert package.is_file
    assert package.user == agents_user
    metadata = json.loads(package.content_string)
    assert metadata["name"] == "pi-web-access"
    latest = json.loads(host.check_output("/usr/bin/npm view pi-web-access@latest version --json"))
    assert metadata["version"] == latest


def test_pi_web_access_is_registered_once_in_user_settings(host, agents_user, agents_home):
    settings = host.file(f"{agents_home}/.pi/agent/settings.json")
    assert settings.user == agents_user
    package = host.file(f"{agents_home}/.pi/agent/npm/node_modules/pi-web-access/package.json")
    metadata = json.loads(package.content_string)
    packages = json.loads(settings.content_string)["packages"]
    sources = [entry if isinstance(entry, str) else entry["source"] for entry in packages]
    web_sources = [source for source in sources if source.startswith("npm:pi-web-access@")]
    assert web_sources == [f"npm:pi-web-access@{metadata['version']}"]


def test_pi_loads_the_web_access_tools_without_extension_errors(host, agents_user, agents_home):
    script = """
        import { DefaultResourceLoader } from
            '__HOME__/.local/lib/node_modules/@earendil-works/pi-coding-agent/dist/index.js';
        const loader = new DefaultResourceLoader({
            cwd: '__HOME__', agentDir: '__HOME__/.pi/agent'
        });
        await loader.reload();
        const result = loader.getExtensions();
        const tools = result.extensions
            .filter(extension => extension.path.includes('/pi-web-access/'))
            .flatMap(extension => [...extension.tools.keys()]);
        console.log(JSON.stringify({errors: result.errors, tools}));
    """.replace("__HOME__", agents_home)
    result = host.run(
        "sudo -u %s -H env PI_OFFLINE=1 timeout 30 /usr/bin/node --input-type=module -e %s",
        agents_user, script,
    )
    assert result.rc == 0, result.stderr
    loaded = json.loads(result.stdout)
    assert not loaded["errors"]
    assert {"web_search", "source_check", "fetch_content", "get_search_content"} <= set(loaded["tools"])
