import torch
from torch.nn import functional as F

class Decoder:
    def __init__(self, llm, rm, weight=0., num_beams=5, topk=5, max_new_token=1024, method="greedy", temperature=0.7):
        self.llm = llm
        self.rm = rm
        self.weight = weight
        self.num_beams = num_beams
        self.topk = topk
        self.max_new_token = max_new_token
        self.method = method
        self.temperature = temperature

    def generate(self, prompt:str, prompt_input:dict):
        model_inputs = self.llm.tokenizer([prompt], return_tensors="pt").to(self.llm.device)
        outputs = self.llm.model.generate(
            **model_inputs,
            max_new_tokens=self.max_new_token,
            num_beams=self.num_beams,
            num_return_sequences=self.topk,
            return_dict_in_generate=True,
            output_scores=True,
        )
        sequences_ids = outputs.sequences
        sequences_scores = outputs.sequences_scores
        # re score the sequences with the RM
        sequences_decoded = self.llm.tokenizer.batch_decode(sequences_ids, skip_special_tokens=True)
        for i, seq in enumerate(sequences_decoded):
            print(f"Sequence {i}: {seq}")
            rm_score = self.rm(sequences_decoded[i], **prompt_input)
            print(f"RM score: {rm_score}")
            sequences_scores[i] += self.weight * rm_score
        if self.method == "greedy":
            best_sequence = sequences_decoded[torch.argmax(sequences_scores)]
        elif self.method == "sample":
            best_sequence = sequences_decoded[torch.multinomial(F.softmax(sequences_scores / self.temperature, dim=-1), num_samples=1)]
        else:
            raise ValueError(f"Invalid method '{self.method}'")
        return best_sequence


            


