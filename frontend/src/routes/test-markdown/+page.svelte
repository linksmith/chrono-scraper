<script>
	import MarkdownRenderer from '$lib/components/ui/markdown-renderer.svelte';
	
	const sampleMarkdown = `
# Heading 1
## Heading 2
### Heading 3

This is a **bold** text and this is *italic* text.

Here's a list:
- Item 1
- Item 2
- Item 3

Ordered list:
1. First item
2. Second item
3. Third item

> This is a blockquote with some important text.

Here's a [link](https://example.com) to example.com.

\`\`\`javascript
// Code block
function hello() {
    console.log("Hello, World!");
}
\`\`\`

And here's some inline \`code\`.

| Table | Header |
|-------|--------|
| Cell 1 | Cell 2 |
| Cell 3 | Cell 4 |

---

That's all for the test!
`;

	const truncatedSample = `
This is a long paragraph that will be truncated. Lorem ipsum dolor sit amet, consectetur adipiscing elit. Sed do eiusmod tempor incididunt ut labore et dolore magna aliqua. Ut enim ad minim veniam, quis nostrud exercitation ullamco laboris nisi ut aliquip ex ea commodo consequat. Duis aute irure dolor in reprehenderit in voluptate velit esse cillum dolore eu fugiat nulla pariatur.
`;
</script>

<div class="container mx-auto p-8 space-y-8">
	<h1 class="text-3xl font-bold mb-4">Markdown Renderer Test</h1>
	
	<div class="grid gap-8 md:grid-cols-2">
		<div>
			<h2 class="text-xl font-semibold mb-2">Full Markdown Rendering</h2>
			<div class="border rounded-lg p-4 bg-background">
				<MarkdownRenderer source={sampleMarkdown} />
			</div>
		</div>
		
		<div>
			<h2 class="text-xl font-semibold mb-2">Truncated Markdown (300 chars)</h2>
			<div class="border rounded-lg p-4 bg-background">
				<MarkdownRenderer 
					source={truncatedSample} 
					truncate={true}
					maxLength={150}
				/>
			</div>
		</div>
	</div>
	
	<div>
		<h2 class="text-xl font-semibold mb-2">Raw Markdown Source</h2>
		<pre class="border rounded-lg p-4 bg-muted overflow-x-auto">
{sampleMarkdown}
		</pre>
	</div>
</div>