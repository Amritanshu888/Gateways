#!/usr/bin/env python
# coding: utf-8

# # Module 4 -- A/B Testing and Traffic Splitting
# 

# ---
# # Part 1 -- Theory: What is A/B Testing for LLMs?
# ---
# 
# ## 1.1 -- Why A/B Testing Matters for LLM Applications

# ![image.png](attachment:image.png)

# We start with **static** because it is simple and teaches the core concepts.  
# Adaptive testing builds on top of static -- same idea, automated weight adjustment.
# 
# > Note: The `weight` field is deprecated in TensorZero 2026.6+.  
# > The new approach uses the `[functions.name.experimentation]` section.  
# > We cover both in this module -- `weight` first for clarity, then the new syntax.

# In[1]:


# ─────────────────────────────────────────────────────────────────
# CELL 1: Setup
# ─────────────────────────────────────────────────────────────────
from pathlib import Path
import subprocess, time, urllib.request

project_dir = Path("tensorzero-demo")
config_dir  = project_dir / "config"

assert (project_dir / "docker-compose.yml").exists(), "Run Module 1 first!"

GATEWAY_URL = "http://localhost:3000"

def restart_gateway():
    subprocess.run(["docker", "compose", "restart", "gateway"],
                   cwd=str(project_dir.resolve()), capture_output=True)
    for _ in range(20):
        try:
            urllib.request.urlopen(f"{GATEWAY_URL}/health", timeout=2)
            print("Gateway healthy.")
            return
        except Exception:
            time.sleep(1)
    print("Gateway did not come up.")

print("Setup complete.")


# ---
# # Part 2 -- Static A/B Test: Split Traffic Between Variants
# ---
# 
# ## 2.1 -- Configuring Two Variants with Equal Weight
# 
# We will create a `chat_ab` function with two variants:
# - **gpt_variant**: OpenAI gpt-4o-mini
# - **groq_variant**: Groq llama-3.1-8b-instant
# 
# Both start with `weight = 0.5` -- 50% of traffic goes to each.
# 
# ```toml
# [functions.chat_ab]
# type = "chat"
# 
# [functions.chat_ab.variants.gpt_variant]
# type  = "chat_completion"
# model = "openai::gpt-4o-mini"
# weight = 0.5           # 50% of traffic
# 
# [functions.chat_ab.variants.groq_variant]
# type  = "chat_completion"
# model = "groq::llama-3.1-8b-instant"
# weight = 0.5           # 50% of traffic
# ```
# 
# We also define **metrics** -- these are what you use to measure variant quality.  
# Without metrics you cannot send feedback, and without feedback you cannot optimize.
# 
# ```toml
# [metrics.thumbs_up]
# type     = "boolean"    # true = good, false = bad
# level    = "inference"  # feedback is per-inference (not per-episode)
# optimize = "max"        # higher is better
# 
# [metrics.response_quality]
# type     = "float"      # 0.0 to 1.0 score
# level    = "inference"
# optimize = "max"
# ```

# In[2]:


# ─────────────────────────────────────────────────────────────────
# CELL 2: Write tensorzero.toml with A/B test configuration
# ─────────────────────────────────────────────────────────────────

tensorzero_toml = """\
# ================================================================
# tensorzero.toml -- Module 4: A/B Testing
# ================================================================


# ── Previous functions (kept) ────────────────────────────────────

[functions.chat]
type = "chat"

[functions.chat.variants.gpt_mini]
type  = "chat_completion"
model = "openai::gpt-4o-mini"


# ================================================================
# MODULE 4 -- METRICS
# Metrics define what you are measuring.
# You must define metrics before sending feedback.
# ================================================================

# Boolean metric: simple thumbs up / thumbs down
[metrics.thumbs_up]
type     = "boolean"
level    = "inference"
optimize = "max"

# Float metric: quality score between 0.0 and 1.0
[metrics.response_quality]
type     = "float"
level    = "inference"
optimize = "max"


# ================================================================
# MODULE 4 -- A/B TEST FUNCTION
# chat_ab: same task, two different implementations.
# weight = 0.5 means 50% of traffic goes to each variant.
# ================================================================

[functions.chat_ab]
type = "chat"

# Variant A: OpenAI gpt-4o-mini
[functions.chat_ab.variants.gpt_variant]
type   = "chat_completion"
model  = "openai::gpt-4o-mini"
weight = 0.5

# Variant B: Groq Llama-3.1-8B
[functions.chat_ab.variants.groq_variant]
type   = "chat_completion"
model  = "groq::llama-3.1-8b-instant"
weight = 0.5
"""

(config_dir / "tensorzero.toml").write_text(tensorzero_toml, encoding="utf-8")
print("Written: config/tensorzero.toml")
print()
print("Metrics defined:")
print("  thumbs_up        (boolean, inference-level)")
print("  response_quality (float,   inference-level)")
print()
print("A/B function defined:")
print("  chat_ab --> gpt_variant (50%) | groq_variant (50%)")

restart_gateway()


# ## 2.2 -- Firing Requests and Observing Traffic Distribution
# 
# We will fire 20 requests at `chat_ab` and count how many go to each variant.
# 
# With `weight = 0.5` on both variants, we expect approximately 50% each.  
# With 20 requests the split will be close to 10/10 but not exactly -- that is normal.  
# With more requests (100+) the distribution converges to the configured weights.
# 
# The key field to watch: **`result.variant_name`** -- TensorZero tells you which variant served each request.

# In[3]:


# ─────────────────────────────────────────────────────────────────
# CELL 3: Fire 20 requests, count variant distribution (50/50)
# ─────────────────────────────────────────────────────────────────
from tensorzero import TensorZeroGateway
from collections import Counter

PROMPT = "In one sentence, what is an LLM gateway?"
N = 20

print(f"Firing {N} requests at chat_ab (weights: gpt=0.5, groq=0.5)")
print()

variant_counts = Counter()
inference_ids  = []  # save for feedback demo later
variant_log    = []

with TensorZeroGateway.build_http(gateway_url=GATEWAY_URL) as client:
    for i in range(N):
        result = client.inference(
            function_name="chat_ab",
            input={"messages": [{"role": "user", "content": PROMPT}]}
        )
        variant_counts[result.variant_name] += 1
        inference_ids.append(result.inference_id)
        variant_log.append(result.variant_name)
        print(f"  [{i+1:2d}] {result.variant_name}")

print()
print("=" * 40)
print("RESULTS -- 50/50 split")
print("=" * 40)
for variant, count in sorted(variant_counts.items()):
    pct = (count / N) * 100
    bar = "#" * count
    print(f"  {variant:<20} {count:2d}/{N}  ({pct:.0f}%)  {bar}")
print()
print(f"Expected: ~{N//2} each. Actual distribution shown above.")
print("With more requests the split converges to exactly 50/50.")


# ## 2.3 -- Changing Weights to 80/20 (Zero Code Change)
# 
# Now we change the traffic split to **80% OpenAI, 20% Groq**.  
# This simulates a scenario where you want to:
# - Gradually roll back Groq if quality is lower
# - Do a small canary test (keep 20% on Groq while mostly using OpenAI)
# - Shift traffic after seeing A/B results
# 
# **The only change is two numbers in `tensorzero.toml`.**  
# Your application code that calls `chat_ab` does not change at all.

# In[4]:


# ─────────────────────────────────────────────────────────────────
# CELL 4: Change weights to 80/20 and repeat
# Only the weight values change -- everything else is identical
# ─────────────────────────────────────────────────────────────────

def update_weights(gpt_weight: float, groq_weight: float):
    """Update chat_ab variant weights in tensorzero.toml and restart gateway."""
    toml = (config_dir / "tensorzero.toml").read_text(encoding="utf-8")

    # Replace weight lines for each variant
    lines = toml.splitlines()
    new_lines = []
    in_gpt = False
    in_groq = False
    for line in lines:
        if "[functions.chat_ab.variants.gpt_variant]" in line:
            in_gpt, in_groq = True, False
        elif "[functions.chat_ab.variants.groq_variant]" in line:
            in_gpt, in_groq = False, True
        elif line.startswith("["):
            in_gpt, in_groq = False, False

        if line.strip().startswith("weight") and in_gpt:
            line = f"weight = {gpt_weight}"
        elif line.strip().startswith("weight") and in_groq:
            line = f"weight = {groq_weight}"
        new_lines.append(line)

    (config_dir / "tensorzero.toml").write_text("\n".join(new_lines), encoding="utf-8")
    restart_gateway()


print("Changing weights: gpt_variant=0.8, groq_variant=0.2")
update_weights(0.8, 0.2)
print()

print(f"Firing {N} requests at chat_ab (weights: gpt=0.8, groq=0.2)")
print()

variant_counts_80 = Counter()

with TensorZeroGateway.build_http(gateway_url=GATEWAY_URL) as client:
    for i in range(N):
        result = client.inference(
            function_name="chat_ab",
            input={"messages": [{"role": "user", "content": PROMPT}]}
        )
        variant_counts_80[result.variant_name] += 1
        print(f"  [{i+1:2d}] {result.variant_name}")

print()
print("=" * 40)
print("RESULTS -- 80/20 split")
print("=" * 40)
for variant, count in sorted(variant_counts_80.items()):
    pct = (count / N) * 100
    bar = "#" * count
    print(f"  {variant:<20} {count:2d}/{N}  ({pct:.0f}%)  {bar}")
print()
print("Application code was IDENTICAL to Cell 3.")
print("Only the TOML config changed -- no code change, no redeployment.")


# ## 2.4 -- Comparing the Two Splits
# 
# This cell shows the before/after comparison side by side.

# In[5]:


# ─────────────────────────────────────────────────────────────────
# CELL 5: Side-by-side comparison of the two splits
# ─────────────────────────────────────────────────────────────────

print(f"{'Variant':<22} {'50/50':>8} {'80/20':>8}")
print("-" * 42)

all_variants = set(variant_counts.keys()) | set(variant_counts_80.keys())
for v in sorted(all_variants):
    c1 = variant_counts.get(v, 0)
    c2 = variant_counts_80.get(v, 0)
    print(f"  {v:<20} {c1:>5}/{N}   {c2:>5}/{N}")

print()
print("Key insight:")
print("  Same function name 'chat_ab' called in identical app code.")
print("  Gateway routed traffic differently based on TOML config alone.")
print("  This is how you do safe rollouts and rollbacks in production.")


# ## Understanding Routing Weights
# 
# ### What Happened?
# 
# #### 50/50 Weights
# 
# Out of 20 requests:
# 
# - 13 requests went to GPT
# - 7 requests went to Groq
# 
# #### 80/20 Weights
# 
# Out of 20 requests:
# 
# - 14 requests went to GPT
# - 6 requests went to Groq
# 
# At first glance, the numbers look very similar.
# 
# That's because **20 requests is a small sample size**. Randomness has a large impact when the number of requests is low.
# 
# ### Why the Difference Isn't Obvious Yet
# 
# With only **20 requests**, you should not expect the distribution to perfectly match the configured weights.
# 
# For example:
# 
# - A 50/50 split does not guarantee exactly 10 GPT and 10 Groq requests.
# - An 80/20 split does not guarantee exactly 16 GPT and 4 Groq requests.
# 
# As the number of requests increases, the observed distribution gets closer to the configured weights.
# 
# For example, with **1000 requests**:
# 
# | Weight Configuration | Expected GPT Requests | Expected Groq Requests |
# |----------|----------:|----------:|
# | 50/50 | ~500 | ~500 |
# | 80/20 | ~800 | ~200 |
# 
# Now the difference becomes very obvious.
# 
# ---
# 
# ## The Real-World Picture
# 
# Imagine your application receives **1000 users per day** hitting the same endpoint.
# 
# ### 50/50 Configuration
# 
# ```text
# ~500 users → GPT-4o-mini
# ~500 users → Groq Llama
# ```
# 
# This is useful for **A/B testing**.
# 
# You can compare:
# 
# - User satisfaction
# - Response quality
# - Latency
# - Cost
# - Conversion rates
# 
# and determine which model performs better.
# 
# ### 80/20 Configuration
# 
# ```text
# ~800 users → GPT-4o-mini  (primary, trusted model)
# ~200 users → Groq Llama   (canary/test model)
# ```
# 
# This is useful for **gradual rollout**.
# 
# You keep most traffic on the proven model while exposing a smaller percentage of users to the new model.
# 
# Benefits:
# 
# - Lower risk
# - Real production data
# - Easy performance comparison
# - Safe experimentation
# 
# ---
# 

# ---
# # Part 3 -- Consistent Episodes: Routing Lock-in for Multi-turn Chats
# ---
# 
# ## 3.1 -- The Problem with A/B Tests in Multi-turn Conversations
# 

# ![image.png](attachment:image.png)

# In[6]:


# ─────────────────────────────────────────────────────────────────
# CELL 6: Restore 50/50 weights for this demo
# ─────────────────────────────────────────────────────────────────
update_weights(0.5, 0.5)
print("Weights restored to 50/50.")


# In[7]:


# ─────────────────────────────────────────────────────────────────
# CELL 7: Demonstrate episode-level variant locking
# Start multiple episodes, show each stays on its assigned variant
# ─────────────────────────────────────────────────────────────────
from tensorzero import TensorZeroGateway

QUESTIONS = [
    "What is an LLM gateway?",
    "What are the benefits of using one?",
    "How does TensorZero compare to others?",
]

with TensorZeroGateway.build_http(gateway_url=GATEWAY_URL) as client:

    # Run 3 separate sessions to show different variants assigned
    for session_num in range(1, 4):
        print(f"=== Session {session_num} ===")

        episode_id = None
        for turn_num, question in enumerate(QUESTIONS, 1):

            kwargs = {
                "function_name": "chat_ab",
                "input": {"messages": [{"role": "user", "content": question}]}
            }
            if episode_id:
                kwargs["episode_id"] = episode_id

            result = client.inference(**kwargs)

            if turn_num == 1:
                episode_id = result.episode_id   # lock from Turn 1

            print(f"  Turn {turn_num}: variant={result.variant_name}  "
                  f"episode={str(result.episode_id)[:8]}...")

        print(f"  All 3 turns used the SAME variant: {result.variant_name}")
        print()

print("Key observation:")
print("  Each session may land on a different variant (50/50 split).")
print("  But within a session, ALL turns always use the SAME variant.")
print("  This is episode-level routing lock-in.")


# ## 3.3 -- Why This is Critical for A/B Test Quality
# 
# ```
# Without episode locking:              With episode locking:
# 
# Session A: GPT turn 1                 Session A: GPT all turns
#            Groq turn 2                           --> feedback = GPT
#            GPT turn 3
#            --> feedback = ???         Session B: Groq all turns
#                mixed signal                      --> feedback = Groq
# ```
# 
# With locking, every piece of feedback is cleanly attributed to one variant.  
# This is what makes TensorZero's optimization reliable -- clean signal, no noise.
# 
# **In practice:** Always pass `episode_id` in multi-turn applications.  
# For single-turn apps (one question, one answer) it does not matter.

# ---
# # Part 4 -- Sending Feedback to Close the Loop
# ---
# 
# ## 4.1 -- The Feedback Loop
# 
# A/B testing without feedback is just traffic splitting.  
# Feedback is what turns traffic splitting into **learning**.
# 
# ```
# The Feedback Loop:
# 
# 1. User sends message
# 2. Gateway routes to variant A or B
# 3. Model returns response
# 4. User reacts (likes, ignores, complaints, buys, clicks)
# 5. YOU send that signal to TensorZero as feedback
#       feedback(inference_id=..., metric_name="thumbs_up", value=True)
# 6. TensorZero stores: this inference, this variant, this outcome
# 7. Over time: "variant A gets 73% thumbs up, variant B gets 61%"
# 8. You shift traffic: variant A gets more weight
# 9. (Advanced) Adaptive mode: gateway shifts traffic automatically
# ```
# 
# ## 4.2 -- Two Types of Feedback Metrics
# 
# **Boolean metric** -- binary signal:
# ```python
# # User clicked thumbs up
# client.feedback(inference_id=id, metric_name="thumbs_up", value=True)
# 
# # User clicked thumbs down
# client.feedback(inference_id=id, metric_name="thumbs_up", value=False)
# ```
# 
# **Float metric** -- graded signal:
# ```python
# # Automated evaluation: quality score from 0.0 to 1.0
# client.feedback(inference_id=id, metric_name="response_quality", value=0.85)
# ```
# 
# Float metrics are powerful for automated evaluation pipelines --  
# you run a separate LLM evaluator that scores each response,  
# then send that score as feedback without waiting for user input.

# In[8]:


# ─────────────────────────────────────────────────────────────────
# CELL 8: Send feedback on inferences from Cell 3
# We saved inference_ids and variant_log earlier.
# Now simulate user feedback: GPT responses rated higher.
# ─────────────────────────────────────────────────────────────────
from tensorzero import TensorZeroGateway

print("Sending feedback for the 20 inferences from Cell 3")
print("Simulating: gpt_variant responses rated higher by users")
print()

feedback_results = []

with TensorZeroGateway.build_http(gateway_url=GATEWAY_URL) as client:

    for i, (inf_id, variant) in enumerate(zip(inference_ids, variant_log)):

        # Simulate: GPT responses get thumbs up 80% of the time
        #           Groq responses get thumbs up 40% of the time
        import random
        random.seed(i)
        if variant == "gpt_variant":
            thumbs_up_value = random.random() < 0.8
            quality_score   = round(random.uniform(0.7, 1.0), 2)
        else:
            thumbs_up_value = random.random() < 0.4
            quality_score   = round(random.uniform(0.3, 0.7), 2)

        # Send boolean feedback
        fb1 = client.feedback(
            inference_id=inf_id,
            metric_name="thumbs_up",
            value=thumbs_up_value
        )

        # Send float feedback
        fb2 = client.feedback(
            inference_id=inf_id,
            metric_name="response_quality",
            value=quality_score
        )

        feedback_results.append({
            "variant":     variant,
            "thumbs_up":   thumbs_up_value,
            "quality":     quality_score,
            "feedback_id": str(fb1.feedback_id)[:8]
        })

        print(f"  [{i+1:2d}] {variant:<20} "
              f"thumbs={'UP  ' if thumbs_up_value else 'DOWN'}  "
              f"quality={quality_score:.2f}  "
              f"feedback_id={feedback_results[-1]['feedback_id']}...")

print()
print("All feedback sent. Stored in PostgreSQL.")


# In[9]:


# ─────────────────────────────────────────────────────────────────
# CELL 9: Analyze feedback results by variant
# ─────────────────────────────────────────────────────────────────

from collections import defaultdict

stats = defaultdict(lambda: {"thumbs_up": [], "quality": []})
for fb in feedback_results:
    stats[fb["variant"]]["thumbs_up"].append(fb["thumbs_up"])
    stats[fb["variant"]]["quality"].append(fb["quality"])

print("=" * 55)
print("  FEEDBACK ANALYSIS BY VARIANT")
print("=" * 55)

for variant, data in sorted(stats.items()):
    n = len(data["thumbs_up"])
    ups = sum(data["thumbs_up"])
    avg_quality = sum(data["quality"]) / n if n else 0
    print(f"  {variant}")
    print(f"    Requests:       {n}")
    print(f"    Thumbs up:      {ups}/{n}  ({ups/n*100:.0f}%)")
    print(f"    Avg quality:    {avg_quality:.2f}")
    print()

print("Based on this data, what should you do with the weights?")
print("  --> The variant with higher feedback scores should get more traffic.")
print("  --> Change weights in tensorzero.toml, restart gateway.")
print("  --> Or let adaptive experimentation handle it automatically (Part 5).")


# ---
# # Part 5 -- The New Experimentation Syntax (Adaptive A/B)
# ---
# 
# ## 5.1 -- From Manual Weights to Automatic Optimization
# 
# The `weight` field we used in Parts 2-4 is **deprecated in TensorZero 2026.6+**.  
# The replacement is the `[functions.name.experimentation]` section.
# 
# More importantly, the new syntax supports **adaptive A/B testing** --  
# the gateway automatically shifts traffic toward better-performing variants  
# based on the feedback you send.
# 
# ```
# Static A/B (weight field):
#   You set 50/50. It stays 50/50 forever until you manually change it.
#   You have to watch the metrics and update weights yourself.
# 
# Adaptive A/B (experimentation section):
#   You set "optimize for thumbs_up".
#   Gateway starts at 50/50.
#   As feedback comes in, gateway automatically shifts toward the winner.
#   After 100 requests: maybe 70/30. After 500: maybe 90/10.
#   You never manually update weights again.
# ```
# 
# ## 5.2 -- The New TOML Syntax
# 
# Old approach (deprecated, still works with warning):
# ```toml
# [functions.chat_ab.variants.gpt_variant]
# weight = 0.5
# 
# [functions.chat_ab.variants.groq_variant]
# weight = 0.5
# ```
# 
# New approach (correct for 2026.6+):
# ```toml
# [functions.chat_ab.experimentation]
# type               = "adaptive"
# candidate_variants = ["gpt_variant", "groq_variant"]
# metric             = "thumbs_up"     # metric to optimize
# update_period_s    = 60             # recalculate weights every 60 seconds
# ```
# 
# No `weight` field needed on variants -- the gateway manages weights automatically.

# In[10]:


# ─────────────────────────────────────────────────────────────────
# CELL 10: Write tensorzero.toml with adaptive experimentation
# This is the correct modern syntax replacing the weight field.
# ─────────────────────────────────────────────────────────────────

adaptive_toml = """\
# ================================================================
# tensorzero.toml -- Module 4: Adaptive A/B Testing
# ================================================================

[functions.chat]
type = "chat"

[functions.chat.variants.gpt_mini]
type  = "chat_completion"
model = "openai::gpt-4o-mini"


# ── Metrics ─────────────────────────────────────────────────────

[metrics.thumbs_up]
type     = "boolean"
level    = "inference"
optimize = "max"

[metrics.response_quality]
type     = "float"
level    = "inference"
optimize = "max"


# ── chat_ab with adaptive experimentation ───────────────────────
# Variants defined WITHOUT weight field.
# [functions.chat_ab.experimentation] controls traffic allocation.

[functions.chat_ab]
type = "chat"

[functions.chat_ab.variants.gpt_variant]
type  = "chat_completion"
model = "openai::gpt-4o-mini"

[functions.chat_ab.variants.groq_variant]
type  = "chat_completion"
model = "groq::llama-3.1-8b-instant"

# The gateway automatically shifts traffic toward the variant
# with higher thumbs_up scores as feedback comes in.
[functions.chat_ab.experimentation]
type               = "adaptive"
candidate_variants = ["gpt_variant", "groq_variant"]
metric             = "thumbs_up"
update_period_s    = 60
"""

(config_dir / "tensorzero.toml").write_text(adaptive_toml, encoding="utf-8")
print("Written: config/tensorzero.toml (adaptive experimentation)")
restart_gateway()
print()
print("How it works now:")
print("  1. Gateway starts with equal split between gpt_variant and groq_variant")
print("  2. You send feedback on each inference (thumbs_up metric)")
print("  3. Every 60 seconds, gateway recalculates weights based on feedback")
print("  4. Better-performing variant gets more traffic automatically")
print("  5. No manual weight changes needed ever again")


# In[11]:


# ─────────────────────────────────────────────────────────────────
# CELL 11: Demo adaptive experimentation
# Send requests + feedback. Show variant distribution over time.
# ─────────────────────────────────────────────────────────────────
from tensorzero import TensorZeroGateway
from collections import Counter
import random

ROUNDS = 3   # 3 rounds of 10 requests each
PER_ROUND = 10

with TensorZeroGateway.build_http(gateway_url=GATEWAY_URL) as client:

    for round_num in range(1, ROUNDS + 1):
        print(f"Round {round_num} ({PER_ROUND} requests + feedback):")

        round_counts = Counter()
        round_inf_ids = []
        round_variants = []

        for i in range(PER_ROUND):
            result = client.inference(
                function_name="chat_ab",
                input={"messages": [{"role": "user",
                                     "content": "What is an LLM gateway?"}]}
            )
            round_counts[result.variant_name] += 1
            round_inf_ids.append(result.inference_id)
            round_variants.append(result.variant_name)

        # Send feedback: GPT rated higher
        for inf_id, variant in zip(round_inf_ids, round_variants):
            random.seed(hash(str(inf_id)))
            value = random.random() < (0.8 if variant == "gpt_variant" else 0.3)
            client.feedback(
                inference_id=inf_id,
                metric_name="thumbs_up",
                value=value
            )

        for variant, count in sorted(round_counts.items()):
            bar = "#" * count
            print(f"  {variant:<22} {count}/{PER_ROUND}  {bar}")
        print()

        if round_num < ROUNDS:
            print("  Waiting 65s for gateway to update weights...")
            time.sleep(65)

print("Over rounds, gpt_variant should receive more traffic")
print("as the gateway learns it gets higher thumbs_up scores.")
print("(With only 10 requests/round and randomness, the trend may take more rounds.)")


# In[ ]:




