import streamlit as st
import hashlib
import time
import os
import json
import pandas as pd

from viz import visualize_common_prefixes
from search import parallel_lloom_search, get_model_name

STARTING_STORIES = [
    "Alice and James unexpectedly connect over a shared love for the Dusty Tome an old bookstore nestled on the edge of town. The scent of aging paper and leather bound Alice in a warm embrace as she browsed the labyrinthine aisles, it was her haven.",
    "It was after nightfall when, wet and tired, Fred and Dan came at last to the river crossing, and they found the way barred. At either end of the bridge there was a police car and on the further side of the river they could see that some new houses had been built: two-storeyed with narrow straight-sided windows, bare and dimly lit, all very gloomy making it uncrossable. A voice shouted in the dark, and they turned and ran, in spite of the chilly wind they were soon puffing and sweating. At the petrol station they gave it up. They had done nearly a mile. They were hungry and footsore.",
    "His body was strong and solid against mine, making me feel safe and protected. I melted into his embrace and everything else faded away, I could feel my whole body trembling with anticipation"
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

def main():

    st.set_page_config(layout='wide', page_title='The LLooM')
    st.markdown("""
            <style>
                .block-container {
                        padding-top: 2rem;
                        padding-bottom: 0rem;
                        padding-left: 3rem;
                        padding-right: 3.5rem;
                    }
                .row-widget {
                    padding-top: 0rem;
                }
            </style>
            """, unsafe_allow_html=True)
            
    if 'page' not in st.session_state:
        st.session_state.page = 0
        st.session_state.threads = None
        
    logo, config = st.columns((1,5))
    logo.markdown("### The LLooM :green[v0.3]")

    with config.expander('Configuration', expanded=False):
        config_cols = st.columns((1,1))
        config_cols[0].markdown('_Stop conditions_')
        story_depth = config_cols[0].checkbox("Auto-Stop (early terminate if a period or comma is encountered)", value=False)
        depth = config_cols[0].number_input("Maximum Depth", min_value=1, max_value=50, value=6, help="Terminate a sugguestion when it gets this long")
        maxsuggestions = config_cols[0].number_input("Beam Limit", min_value=5, max_value=100, value=100, help="Stop spawning new beams when the number of suggestions hits this limit")
        
        config_cols[1].markdown('_Split conditions_\n\nLower the Cutoff to get more variety (at the expense of quality and speed), raise Cutoff for a smaller number of better suggestions.')
        cutoff = config_cols[1].number_input("Cutoff", help="Minimum propability of a token to have it split a new suggestion beam", min_value=0.0, max_value=1.0, value=0.1, step=0.01)
        multiplier = config_cols[1].number_input("Multiplier", help="The cutoff is scaled by Multiplier each time a new token is generated", min_value=0.0, max_value=2.0, value=1.0, step=0.1)
        maxsplits = config_cols[1].number_input("Split Limit", help="The maximum number of splits from a single source token, raise to get more variety.", min_value=0, max_value=10, value=3)
        
    left, right = st.columns((2,3))
       
    if st.session_state.page == 0:
        st.write('Open the Configuration panel above to adjust settings, Auto-depth mode is particularly useful at the expense of longer generation speeds. You will be able to change settings at any point and regenerate suggestions.\n\nThe starting prompts below are just suggestions, once inside the playground you can fully edit the prompt.')
        start_prompt = st.selectbox("Start Prompt", STARTING_STORIES, index=0)
        if st.button("Start"):
            st.session_state.story_so_far = start_prompt
            st.session_state.page = 1
            st.rerun()
    else:
        story_so_far = st.session_state.story_so_far        
        new_story_so_far = left.text_area("Story so far", story_so_far, label_visibility='hidden', height=300)
        if left.button('Suggest Again'):
            story_so_far = new_story_so_far
            st.session_state.story_so_far = story_so_far
            st.session_state.threads = None
        
        if st.session_state.threads == None:
            please_wait = st.empty()
            t0 = time.time()
            tokens = 0
            
            with please_wait.status('Searching for suggestions, please wait..') as status:
                threads = []
                for thread in parallel_lloom_search(story_so_far, depth, maxsuggestions, ['.',','] if story_depth else [], cutoff, multiplier, maxsplits, LLAMA_PIPELINE_REQUESTS):
                    label = thread[1][len(story_so_far):]
                    status.update(label=label, state="running")
                    threads.append(thread)
                    tokens += thread[2]

                delta = time.time() - t0
                tps = tokens/delta
                status.update(label=f"Search completed, found {len(threads)} suggestion in {delta:.2f}s @ {tps:.2f} tokens/sec", state="complete", expanded=False)
            
            sorted_threads = sorted(threads, key=lambda x: x[0], reverse=True)
            
            # remove duplicate threads
            dedupe = {}
            good_threads = []
            add_space = False
            for prob, thread, depth in sorted_threads:
                new_tokens = thread[len(story_so_far):]
                if new_tokens[0] == ' ': 
                    new_tokens = new_tokens[1:]
                    thread = story_so_far + " " + thread[len(story_so_far):]
                    add_space = True
                if dedupe.get(new_tokens) is None:
                    dedupe[new_tokens] = prob
                    good_threads.append( (prob, new_tokens) )

            st.session_state.threads = good_threads
            st.session_state.sorted_threads = sorted_threads
            st.session_state.add_space = add_space
            
            # if there is only one option - take it.
            if len(good_threads) == 1:
                st.session_state.story_so_far += (" " if add_space else "") + good_threads[0][1]
                st.session_state.threads = None
                st.rerun()  
            
        threads = st.session_state.threads
        add_space = st.session_state.add_space
        json_data = json.dumps(threads)
        modelname = get_model_name()
        dataframe = pd.DataFrame(threads, columns=['Probability', 'Thread'])
        csv_data = dataframe.to_csv(index=False)
        labels = [ thread for prob, thread in threads ]


        story_so_far_words = story_so_far.split()[:3]
        joined_words = "_".join(word.lower() for word in story_so_far_words)
        
        viz = visualize_common_prefixes(labels)
        with right:
            
            st.graphviz_chart(viz)
            st.download_button('Download DOT Graph', viz.source, 'graph.dot', 'text/plain')
            st.download_button('Download PNG', viz.pipe(format='png'), 'graph.png', 'image/png')
            st.download_button('Download JSON', json_data, 'loom_data.'+modelname+'.'+joined_words+'.json', 'application/json')
            st.download_button('Download CSV', csv_data, 'loom_data.'+modelname+'.'+joined_words+'.csv', 'text/csv')         

        controls = st.container()        
        buttons = st.container()
        
        with controls:
            user_add_space = st.checkbox("Prefix space", value=add_space, key=computeMD5hash('prefix-'+story_so_far))
        
        sum_probs = sum([prob for prob, _ in threads])
        with buttons:
            for prob, thread in threads:
                col1, col2 = st.columns((3,1))
                col2.progress(value=prob/sum_probs)
                new_text = col1.text_input(thread, value=thread, key='text-'+computeMD5hash(thread), label_visibility='hidden')
                if col2.button(':arrow_right:', key='ok-'+computeMD5hash(thread)):
                    st.session_state.story_so_far += (" " if user_add_space else "") + new_text
                    st.session_state.threads = None
                    st.rerun()                

if __name__ == "__main__":
    main()
