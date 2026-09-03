.PHONY: build validate clean

BUNDLE := cookidoo-mcp.mcpb

validate:
	uv lock --check
	python3 -m json.tool manifest.json >/dev/null
	npx --yes @anthropic-ai/mcpb validate manifest.json

build: validate
	npx --yes @anthropic-ai/mcpb pack . $(BUNDLE)

clean:
	rm -f $(BUNDLE)
