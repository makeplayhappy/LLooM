import numpy as np
import os
global t_model
openai_client = None
def get_logprobs_openai(prompt, model="gpt-3.5-turbo"):
    global openai_client
    if openai_client is None:
        from openai import OpenAI
        openai_client = OpenAI()
    
    messages = [{'role': 'user', 'content': prompt}]
    response = openai_client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=0.7,
        max_tokens=1,
        logprobs=True,
        top_logprobs=10,
        n=1
    )
    
    top_logprobs = response.choices[0].logprobs.content[0].top_logprobs
    for logprob in top_logprobs:
        logprob.probability = np.exp(logprob.logprob)
        
    return top_logprobs

class SimpleProbability:
    def __init__(self, token, probability):
        self.token = token
        self.probability = probability

def get_model_name():
    if os.getenv('LLAMA_API_URL') is not None:
        import requests
        base_url = os.getenv('LLAMA_API_URL')
        models = requests.get(base_url+'/v1/models').json()
        modelname, extension = os.path.splitext(os.path.basename(models['data'][0]['id'] ))
        return modelname
    
    elif os.getenv('KOBOLD_API_URL') is not None:
        import requests
        base_url = os.getenv('KOBOLD_API_URL')
        models = requests.get(base_url+'/v1/models').json()
        modelname, extension = os.path.splitext(os.path.basename(models['data'][0]['id'] ))
        return modelname
    else:
        return ""

## doh! no log probs from Kobold!
def get_logprobs_kobold(prompt, base_url):
    import requests
       
    url = base_url+'/v1/completions'
    payload = { 'prompt': prompt,
            'cache_prompt': True,
            'temperature': 1.0,
            'n_predict': 1,
            'top_k': 10,
            'top_p': 1.0,
            'n_probs': 10
           }
    
    response = requests.post(url, json=payload)
    response_json = response.json()
    probs = response_json['completion_probabilities'][0]['probs']


    return [ SimpleProbability(prob['tok_str'], prob['prob']) for prob in probs]

def get_logprobs_llama(prompt, base_url):
    import requests
       
    url = base_url+'/completion'
    payload = { 'prompt': prompt,
            'cache_prompt': True,
            'temperature': 1.0,
            'n_predict': 1,
            'top_k': 10,
            'top_p': 1.0,
            'n_probs': 10
           }
    
    response = requests.post(url, json=payload)

    try:
        response_json = response.json()
    
        if 'completion_probabilities' in response_json and response_json['completion_probabilities']:
            if 'probs' in response_json['completion_probabilities'][0]:
                probs = response_json['completion_probabilities'][0]['probs']
            else:
                print("Warning: 'probs' key not found in the first completion probability.")
                probs = []
        else:
            print("Warning: 'completion_probabilities' is empty or not present in the response.")
            probs = []

    except json.JSONDecodeError:
        print("Error: Failed to decode JSON from the response.")
        probs = []
    except IndexError:
        print("Error: 'completion_probabilities' list is empty.")
        probs = []
    except KeyError as e:
        print(f"Error: Expected key not found in JSON response: {e}")
        probs = []
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        probs = []

    # Now you can safely use 'probs'
    #print(f"Number of probabilities: {len(probs)}")
    #print(probs)

    return [ SimpleProbability(prob['tok_str'], prob['prob']) for prob in probs]

vllm_model_name = None
def get_logprobs_vllm(prompt, base_url):
    import requests
    
    global vllm_model_name
    if vllm_model_name is None:
        models = requests.get(base_url+'/v1/models').json()
        vllm_model_name = models['data'][0]['id']
        print('VLLM model name:', vllm_model_name)
       
    url = base_url+'/v1/completions'
    payload = {
        "prompt": prompt,
        "n": 1,
        "temperature": 0.0,
        "max_tokens": 1,
        "stream": False,
        "logprobs": 5,
        "model": vllm_model_name
    }

    response = requests.post(url, json=payload)
    probs = response.json()['choices'][0]['logprobs']['top_logprobs'][0]
    return [ SimpleProbability(k,np.exp(v)) for k,v in probs.items()]

from concurrent.futures import ThreadPoolExecutor, as_completed

def parallel_get_logprobs(prompt, acc):
    # Choose which API to use based on environment variables
    if os.getenv('LLAMA_API_URL') is not None:
        logprobs =  get_logprobs_llama(prompt, os.getenv('LLAMA_API_URL'))
    elif os.getenv('KOBOLD_API_URL') is not None:
        logprobs =  get_logprobs_kobold(prompt, os.getenv('KOBOLD_API_URL'))
    elif os.getenv('VLLM_API_URL') is not None:
        logprobs =  get_logprobs_vllm(prompt, os.getenv('VLLM_API_URL'))
    elif os.getenv('OPENAI_API_KEY') is not None:
        logprobs = get_logprobs_openai(prompt)
    else:
        raise Exception('Please set either OPENAI_API_KEY or LLAMA_API_URL')       
    
    return (prompt, acc, logprobs)

def parallel_lloom_search(initial_prompt, max_depth, max_beams, stop_tokens, initial_cutoff, multiplier, maxsplits, parallelism=2):
    
    tasks = [(initial_prompt, 0.0)]
    cutoff = initial_cutoff
    depth = max_depth
    done_beams = 0

    with ThreadPoolExecutor(max_workers=parallelism) as executor:
        while tasks:
            # spawn futures
            futures = []
            for task in tasks:
                print("spawning depth:", depth ,"task:", task)
                futures.append(executor.submit(parallel_get_logprobs, *task))
                
            total_futures = len(tasks)
            tasks = []
            done_futures = 0

            # process futures as they come in
            for future in as_completed(futures):
                res = future.result()
                (prompt, acc, logprobs) = res

                count = 0
                for logprob_choice in logprobs:
                    token = logprob_choice.token
                    probability = logprob_choice.probability

                    if count > 0 and probability < cutoff: break        
                    if maxsplits > 0 and count == maxsplits: break

                    count += 1

                    new_prompt = prompt + token
                    early_finish = False

                    if depth == 0 or ((max_beams > 0) and (done_beams+total_futures-done_futures >= max_beams)):
                        yield (acc + probability, new_prompt, max_depth - depth)
                        early_finish = True
                    else:
                        new_tokens = new_prompt[len(initial_prompt):]
                        stop_search_tokens = new_tokens
                        
                        for st in stop_tokens:
                            # starting with a stop token is OK, keep searching until there's some meat
                            if stop_search_tokens[0:len(st)] == st: 
                                stop_search_tokens = stop_search_tokens[len(st):]

                            if (not early_finish) and (st in stop_search_tokens):
                                trimmed_prompt = initial_prompt + new_tokens[:new_tokens.find(st)+1]
                                yield (acc + probability, trimmed_prompt, max_depth - depth)
                                early_finish = True

                    if not early_finish:
                        new_task =(new_prompt, acc + probability)
                        tasks.append(new_task)
                    else:
                        done_beams += 1
                        
                done_futures += 1
            
            # adjust for next cycle            
            cutoff = cutoff * multiplier
            depth = depth - 1
