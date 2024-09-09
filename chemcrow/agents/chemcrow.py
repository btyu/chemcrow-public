import os
from typing import Optional

# import langchain
from dotenv import load_dotenv
from langchain import PromptTemplate, chains
from langchain.callbacks.streaming_stdout import StreamingStdOutCallbackHandler
import langchain_openai, langchain_anthropic
from pydantic import ValidationError
from rmrkl import ChatZeroShotAgent, RetryAgentExecutor

from .prompts import FORMAT_INSTRUCTIONS, QUESTION_PROMPT, REPHRASE_TEMPLATE, SUFFIX
from .tools import make_tools


def _make_llm(model, temp, api_keys, streaming: bool = False):
    if model.startswith("gpt-3.5-turbo") or model.startswith("gpt-4"):
        llm = langchain_openai.ChatOpenAI(
            temperature=temp,
            model_name=model,
            request_timeout=1000,
            streaming=streaming,
            callbacks=[StreamingStdOutCallbackHandler()],
            api_key=api_keys['OPENAI_API_KEY'],
        )
    elif model.startswith("text-"):
        raise NotImplementedError("Text models are not supported yet")
        # llm = langchain.OpenAI(
        #     temperature=temp,
        #     model_name=model,
        #     streaming=streaming,
        #     callbacks=[StreamingStdOutCallbackHandler()],
        #     openai_api_key=api_keys['OPENAI_API_KEY'],
        # )
    elif model.startswith('claude'):
        llm = langchain_anthropic.ChatAnthropic(
            temperature=temp,
            model_name=model,
            streaming=streaming,
            callbacks=[StreamingStdOutCallbackHandler()],
            api_key=api_keys['ANTHROPIC_API_KEY'],
        )
    else:
        raise ValueError(f"Invalid model name: {model}")
    return llm


class ChemCrow:
    def __init__(
        self,
        tools=None,
        model="gpt-4-0613",
        tools_model="gpt-3.5-turbo-0613",
        temp=0.1,
        max_iterations=40,
        verbose=True,
        streaming: bool = True,
        api_keys: dict = {},
    ):
        """Initialize ChemCrow agent."""

        load_dotenv()

        openai_api_key = api_keys.get('OPENAI_API_KEY') or os.getenv('OPENAI_API_KEY')
        assert openai_api_key is not None, 'Must set OPENAI_API_KEY'

        try:
            self.llm = _make_llm(model, temp, api_keys, streaming)
        except ValidationError:
            raise ValueError("Invalid OpenAI API key")

        if tools is None:
            tools_llm = _make_llm(tools_model, temp, api_keys, streaming)
            tools = make_tools(tools_llm, api_keys=api_keys, verbose=verbose)

        # Initialize agent
        self.agent_executor = RetryAgentExecutor.from_agent_and_tools(
            tools=tools,
            agent=ChatZeroShotAgent.from_llm_and_tools(
                self.llm,
                tools,
                suffix=SUFFIX,
                format_instructions=FORMAT_INSTRUCTIONS,
                question_prompt=QUESTION_PROMPT,
            ),
            verbose=True,
            max_iterations=max_iterations,
        )

        rephrase = PromptTemplate(
            input_variables=["question", "agent_ans"], template=REPHRASE_TEMPLATE
        )

        self.rephrase_chain = chains.LLMChain(prompt=rephrase, llm=self.llm)

    def run(self, prompt, callbacks=None):
        outputs = self.agent_executor({"input": prompt}, callbacks=callbacks)
        return outputs["output"]
