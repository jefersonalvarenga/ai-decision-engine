import dspy

class AnalystSignature(dspy.Signature):
    """Analyze the conversation history and patient profile to identify ghosting reasons and triggers."""
    customer_name = dspy.InputField()
    ad_source = dspy.InputField()
    psychographic_profile = dspy.InputField(desc="Patient's age, interests, and pain points")
    conversation_history = dspy.InputField(desc="Last exchanges")
    
    analyst_diagnosis = dspy.OutputField(desc="Strategic diagnosis of the current lead state")

class StrategistSignature(dspy.Signature):
    """Select the best re-engagement strategy (SOCIAL_PROOF, EDUCATION, DIRECT_OFFER, CURIOSITY)."""
    analyst_diagnosis = dspy.InputField()
    selected_strategy = dspy.OutputField(desc="Name of the chosen strategy")
    rationale = dspy.OutputField(desc="Why this strategy fits")

class CopywriterSignature(dspy.Signature):
    """
    Write a persuasive WhatsApp message in Portuguese (pt-BR). 
    Focus on empathy, the patient's specific pain point, and the chosen strategy.
    NO hashtags, NO formal letter openings. Use a friendly, conversational WhatsApp tone.
    """
    selected_strategy = dspy.InputField()
    analyst_diagnosis = dspy.InputField()
    generated_copy = dspy.OutputField(desc="The final message in Portuguese")

class CriticSignature(dspy.Signature):
    """Clinical Director review for compliance, empathy, and safety (No direct prescriptions)."""
    generated_copy = dspy.InputField()
    analyst_diagnosis = dspy.InputField()
    
    critic_feedback = dspy.OutputField(desc="Feedback on approval or rejection")
    is_approved = dspy.OutputField(desc="True or False", bool=True)