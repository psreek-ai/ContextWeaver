# ContextWeaver demo recording
# Run with: vhs demo.tape
# Install vhs: https://github.com/charmbracelet/vhs

Output docs/demo.gif

Set Shell "bash"
Set FontSize 14
Set Width 1200
Set Height 650
Set Theme "Dracula"
Set TypingSpeed 40ms
Set Padding 20

# Setup
Hide
Type "export CW_ANTHROPIC_API_KEY=sk-ant-demo && cd /tmp && git clone https://github.com/your-org/contextweaver demo-run && cd demo-run && pip install -e . -q"
Enter
Sleep 3s
Show

# Title
Type "# ContextWeaver — Decision Archaeology"
Sleep 1s
Ctrl+C

# Mine a local repo
Type "contextweaver mine local ."
Enter
Sleep 4s

# Ask why
Type `contextweaver why "Why do we use ChromaDB instead of Pinecone?"`
Enter
Sleep 5s

# Generate a briefing
Type `contextweaver brief "storage layer" --for "new engineer"`
Enter
Sleep 5s

# Conflict check
Type `contextweaver check "We should replace ChromaDB with a simple JSON file for storage"`
Enter
Sleep 5s

# Stats
Type "contextweaver stats"
Enter
Sleep 2s
