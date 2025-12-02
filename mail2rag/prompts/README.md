# Mail2RAG Prompts

This directory contains customizable AI prompts used by the Mail2RAG application.

## Available Prompts

### vision_ai.txt
Main prompt for Vision AI analysis of documents and photos.

**Purpose:** Instructs the Vision AI model on how to analyze images, whether they are documents (invoices, receipts, contracts) or photos (landscapes, events, portraits).

**Customization:**
- Modify the classification criteria
- Adjust metadata extraction fields
- Change output format
- Add language-specific instructions

**Variables:** None (plain text substitution)

## How to Customize

1. **Edit the prompt file** directly
2. **Restart the container** for changes to take effect:
   ```bash
   docker-compose restart mail2rag
   ```
3. **Test with a sample email** containing an image/PDF

## Future Prompts

- `vision_document.txt` - Optimized for document analysis only
- `vision_photo.txt` - Optimized for photo descriptions
- `email_summary.txt` - For summarizing long emails
- `subject_parser.txt` - For extracting structured data from subjects

## Best Practices

✅ Keep prompts focused and clear  
✅ Use structured output formats (Markdown, JSON)  
✅ Test with diverse samples before production  
✅ Version control your custom prompts  
✅ Document any modifications in commit messages
