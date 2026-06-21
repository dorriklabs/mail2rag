class HtmlReporter:
    def __init__(self, original_send_reply):
        self.original_send_reply = original_send_reply

    def generate_and_send(self, results):
        report_lines = []
        report_lines.append("\n" + "="*120)
        report_lines.append("📊 BILAN SYNTHETIQUE QA - MAIL2RAG")
        report_lines.append("="*120)
        
        GREEN = "\033[92m"
        RED = "\033[91m"
        YELLOW = "\033[93m"
        RESET = "\033[0m"
        BOLD = "\033[1m"
        
        # Entête du tableau
        header = f"| {'ID':<15} | {'Type':<13} | {'Sujet':<20} | {'Routage Cible':<25} | {'Latence':<8} | {'Note':<5} | {'Remarque':<40}"
        report_lines.append(header)
        report_lines.append("-" * 120)
        
        rag_tests = 0
        rag_success = 0
        total_score = 0
        failures = []
        
        for r in results:
            note_str = str(r['note']).strip()
            color = RESET
            
            if note_str != "N/A" and note_str != "-":
                try:
                    score = int(note_str.split('/')[0])
                    rag_tests += 1
                    total_score += score
                    if score >= 7:
                        rag_success += 1
                        color = GREEN
                    elif score >= 4:
                        color = YELLOW
                    else:
                        color = RED
                        failures.append(r)
                except:
                    pass
            elif note_str == "-":
                color = "\033[94m" # Blue for ingestion
            
            subj = str(r['subject'])[:20].ljust(20)
            target = str(r['target'])[:25].ljust(25)
            remarque = str(r['remarque'])[:38].ljust(38) + (".." if len(str(r['remarque'])) > 38 else "")
            note_val = note_str[:5].ljust(5)
            lat = str(r['latency'])[:8].ljust(8)
            
            row = f"| {r['id']:<15} | {r['type']:<13} | {subj} | {target} | {lat} | {color}{note_val}{RESET} | {remarque}"
            report_lines.append(row)
            
        report_lines.append("="*120)
        if failures:
            report_lines.append(f"\n{RED}{BOLD}❌ SCÉNARIOS EN ÉCHEC (À ANALYSER POUR AMÉLIORATION){RESET}")
            report_lines.append("-" * 120)
            for f in failures:
                report_lines.append(f"🔴 {BOLD}{f['id']}{RESET} ({f['type']})")
                report_lines.append(f"   Sujet    : {f['subject']}")
                report_lines.append(f"   Cible    : {f['target']}")
                report_lines.append(f"   Note     : {RED}{f['note']}{RESET}")
                
                sources_str = ", ".join(f.get('sources', [])) if f.get('sources') else "Aucune"
                report_lines.append(f"   Sources  : {sources_str}")
                
                report_lines.append(f"   Remarque : {f['remarque']}")
                report_lines.append("-" * 80)
            report_lines.append("="*120)
            
        if rag_tests > 0:
            success_rate = (rag_success/rag_tests)*100
            rate_color = GREEN if success_rate >= 80 else YELLOW if success_rate >= 50 else RED
            report_lines.append(f"🎯 TAUX DE RÉUSSITE RAG : {rate_color}{rag_success}/{rag_tests} scénarios valides ({success_rate:.1f}%){RESET}")
            report_lines.append(f"⭐ NOTE MOYENNE : {rate_color}{total_score/rag_tests:.1f}/10{RESET}")
        report_lines.append("="*120 + "\n")
        
        report_text = "\n".join(report_lines)
        print(report_text)
        
        # Génération du rapport HTML
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
                <td style="padding: 10px; border-bottom: 1px solid #ddd; color: {color}; font-weight: bold;">{r['note']}</td>
                <td style="padding: 10px; border-bottom: 1px solid #ddd; font-size: 0.9em;">{r['remarque']}</td>
            </tr>
            """
            
        success_rate = (rag_success/rag_tests)*100 if rag_tests > 0 else 0
        avg_score = total_score/rag_tests if rag_tests > 0 else 0
        
        html_content = f"""
        <html>
        <head>
            <style>
                body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; color: #333; line-height: 1.6; background-color: #f4f6f8; padding: 20px; }}
                .container {{ max-width: 1000px; margin: 0 auto; background: #fff; padding: 30px; border-radius: 8px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); }}
                h2 {{ color: #2c3e50; border-bottom: 2px solid #3498db; padding-bottom: 10px; }}
                .summary-box {{ background-color: #e8f4f8; padding: 20px; border-left: 5px solid #3498db; border-radius: 4px; margin-bottom: 30px; }}
                .summary-box p {{ margin: 5px 0; font-size: 1.1em; }}
                .highlight {{ font-weight: bold; color: #2980b9; }}
                table {{ width: 100%; border-collapse: collapse; margin-top: 20px; }}
                th {{ background-color: #f8f9fa; color: #333; font-weight: bold; text-align: left; padding: 12px 10px; border-bottom: 2px solid #ddd; }}
                tr:hover {{ background-color: #f1f1f1; }}
            </style>
        </head>
        <body>
            <div class="container">
                <h2>📊 Rapport QA Mail2RAG</h2>
                
                <div class="summary-box">
                    <p>🎯 Taux de réussite RAG : <span class="highlight">{rag_success}/{rag_tests} scénarios valides ({success_rate:.1f}%)</span></p>
                    <p>⭐ Note Moyenne : <span class="highlight">{avg_score:.1f}/10</span></p>
                </div>
                
                <table>
                    <thead>
                        <tr>
                            <th>ID</th>
                            <th>Type</th>
                            <th>Sujet</th>
                            <th>Cible</th>
                            <th>Latence</th>
                            <th>Note</th>
                            <th>Remarque</th>
                        </tr>
                    </thead>
                    <tbody>
                        {html_rows}
                    </tbody>
                </table>
                <br>
                <p style="font-size: 0.9em; color: #7f8c8d; text-align: center;">Généré automatiquement par l'agent de test Mail2RAG.</p>
            </div>
        </body>
        </html>
        """
        
        # Envoi de l'email HTML à l'admin
        try:
            print("📧 Envoi du rapport HTML par email à admin@dsiatlantic.com...")
            self.original_send_reply(
                to_email="admin@dsiatlantic.com",
                subject=f"📊 Rapport QA Mail2RAG - Score: {rag_success}/{rag_tests}",
                body=html_content,
                is_html=True
            )
            print("✅ Rapport HTML envoyé avec succès.")
        except Exception as e:
            print(f"⚠️ Échec de l'envoi du rapport par email : {e}")
