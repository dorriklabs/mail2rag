import json

results = [
    {
        "id": "SUPPORT_SOCIAL_2",
        "type": "Support (RAG)",
        "subject": "Aide financière CCAS",
        "target": "social@dsiatlantic.com",
        "latency": "3.93s",
        "note": "10/10",
        "remarque": "Parfait : Tous les concepts clés sont présents."
    }
]

html_rows = ""
for r in results:
    color = "#4CAF50" if "10/10" in r['note'] else "#FF9800" if "7/10" in r['note'] else "#F44336" if "4/10" in r['note'] or "2/10" in r['note'] else "#9E9E9E"
    html_rows += f"""
    <tr>
        <td style="padding: 10px; border-bottom: 1px solid #ddd;"><strong>{r['id']}</strong></td>
        <td style="padding: 10px; border-bottom: 1px solid #ddd;">{r['type']}</td>
        <td style="padding: 10px; border-bottom: 1px solid #ddd;">{r['subject']}</td>
        <td style="padding: 10px; border-bottom: 1px solid #ddd; font-family: monospace;">{r['target']}</td>
        <td style="padding: 10px; border-bottom: 1px solid #ddd;">{r['latency']}</td>
        <td style="padding: 10px; border-bottom: 1px solid #ddd; color:{color}; font-weight: bold;">{r['note']}</td>
        <td style="padding: 10px; border-bottom: 1px solid #ddd; font-size: 0.9em;">{r['remarque']}</td>
    </tr>
    """

print(html_rows)
