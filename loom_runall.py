import hashlib
import time
import os
import json
import pandas as pd
from search import parallel_lloom_search, get_model_name

STARTING_STORIES = [
    "Alice and James unexpectedly connect over a shared love for the Dusty Tome an old bookstore nestled on the edge of town. The scent of aging paper and leather bound Alice in a warm embrace as she browsed the labyrinthine aisles, it was her haven.",
    "It was after nightfall when, wet and tired, Fred and Dan came at last to the river crossing, and they found the way barred. At either end of the bridge there was a police car and on the further side of the river they could see that some new houses had been built: two-storeyed with narrow straight-sided windows, bare and dimly lit, all very gloomy making it uncrossable. A voice shouted in the dark, and they turned and ran, in spite of the chilly wind they were soon puffing and sweating. At the petrol station they gave it up. They had done nearly a mile. They were hungry and footsore.",
    "His body was strong and solid against mine, making me feel safe and protected. I melted into his embrace and everything else faded away, I could feel my whole body trembling with anticipation",
    "Once upon a time,",
    "The forest seemed darker then usual, but that did not bother Elis in the least.",
    "In the age before man,"
]

LLAMA_PIPELINE_REQUESTS = int(os.getenv('LLAMA_PIPELINE_REQUESTS', 1))
print("LLAMA_PIPELINE_REQUESTS", LLAMA_PIPELINE_REQUESTS)

def computeMD5hash(my_string):
    m = hashlib.md5()
    m.update(my_string.encode('utf-8'))
    return m.hexdigest()

def process_story(story, depth=6, maxsuggestions=50, story_depth=False, cutoff=0.1, multiplier=1.0, maxsplits=3):
    print(f"Processing story: {story[:50]}...")
    t0 = time.time()
    tokens = 0
    
    threads = []
    for thread in parallel_lloom_search(story, depth, maxsuggestions, ['.',','] if story_depth else [], cutoff, multiplier, maxsplits, LLAMA_PIPELINE_REQUESTS):
        label = thread[1][len(story):]
        threads.append(thread)
        tokens += thread[2]

    delta = time.time() - t0
    tps = tokens/delta
    print(f"Search completed, found {len(threads)} suggestions in {delta:.2f}s @ {tps:.2f} tokens/sec")
    
    sorted_threads = sorted(threads, key=lambda x: x[0], reverse=True)
    
    # remove duplicate threads
    dedupe = {}
    good_threads = []
    for prob, thread, depth in sorted_threads:
        new_tokens = thread[len(story):]
        if new_tokens[0] == ' ':
            new_tokens = new_tokens[1:]
            thread = story + " " + thread[len(story):]
        if dedupe.get(new_tokens) is None:
            dedupe[new_tokens] = prob
            good_threads.append((prob, new_tokens))
    
    return good_threads

def main():
    all_results = {}
    modelname = get_model_name()

    for story in STARTING_STORIES:
        story_so_far_words = story.split()[:3]
        joined_words = "_".join(word.lower() for word in story_so_far_words)
        
        threads = process_story(story)
        all_results[joined_words] = threads

    # Prepare data for CSV
    csv_data = []
    for key, threads in all_results.items():
        for prob, thread in threads:
            csv_data.append({
                'Story_Key': key,
                'Probability': prob,
                'Thread': thread
            })

    df = pd.DataFrame(csv_data)
    csv_filename = f'loom_data.{modelname}.csv'
    df.to_csv(csv_filename, index=False)
    print(f"Data saved to {csv_filename}")

if __name__ == "__main__":
    main()
