curl -X POST https://ade.easyscale.co/v1/reengage \
  -H "Content-Type: application/json" \
-d '{
  "lead_name": "Mariana Oliveira",
  "ad_source": "Facebook Ads - Bioestimuladores",
  "psychographic_profile": "Mulher, 35-45 anos, busca rejuvenescimento natural, preocupada com o tempo de recuperação.",
  "conversation_history": "Mariana perguntou se o procedimento dói. Respondemos que usamos anestesia tópica. Ela visualizou e não respondeu há 3 dias."
}'


curl -X POST https://ade.easyscale.co/v1/router \
-H "Content-Type: application/json" \
-d '{
  "message": "[Manter mensagem] Quero saber mais sobre Fotona 20% OFF",
  "context": {
    "patient_name": "Mariana Oliveira",
    "last_interaction": null,
    "active_items": []
  }
}'

curl -X POST https://ade.easyscale.co/v1/router \
-H "Content-Type: application/json" \
     -d '{
           "latest_incoming": "Manter mensagem - Olá, tenho interesse no Fotona 20%OFF",
           "history": [],  # <--- Agora aceita a lista vazia ou com objetos
           "intake_status": "not_started",
           "schedule_status": "not_started",
           "reschedule_status": "not_started",
           "cancel_status": "not_started",
           "language": "pt-BR"
         }'
