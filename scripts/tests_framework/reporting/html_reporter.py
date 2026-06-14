class HtmlReporter:
    def __init__(self, original_send_reply):
        self.original_send_reply = original_send_reply

    def generate_and_send(self, results):
        report_lines = []
        report_lines.append("\n" + "="*140)
        report_lines.append("📊 BILAN SYNTHETIQUE QA - MAIL2RAG")
        report_lines.append("="*140)
        
        # Entête du tableau
        header = f"| {'ID':<15} | {'Type':<15} | {'Sujet':<23} | {'Routage Cible':<25} | {'Latence':<10} | {'Note':<8} | {'Remarque':<20}"
        report_lines.append(header)
        report_lines.append("-" * len(header))
        
        rag_tests = 0
        rag_success = 0
        total_score = 0
        
        for r in results:
            row = f"| {r['id']:<15} | {r['type']:<15} | {r['subject']:<23} | {r['target']:<25} | {r['latency']:<10} | {r['note']:<8} | {r['remarque']:<20}"
            report_lines.append(row)
            
            # Calcul des statistiques (uniquement pour les tests qui ont reçu une note)
            if r['note'] != "N/A" and r['note'] != "-":
                try:
                    score = int(r['note'].split('/')[0])
                    rag_tests += 1
                    total_score += score
                    if score >= 7:
                        rag_success += 1
                except:
                    pass
        
        report_lines.append("="*140)
        if rag_tests > 0:
            report_lines.append(f"🎯 TAUX DE RÉUSSITE RAG : {rag_success}/{rag_tests} scénarios valides ({(rag_success/rag_tests)*100:.1f}%)")
            report_lines.append(f"⭐ NOTE MOYENNE : {total_score/rag_tests:.1f}/10")
        report_lines.append("="*140 + "\n")
        
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
