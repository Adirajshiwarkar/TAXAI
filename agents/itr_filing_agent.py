"""
ITR Filing Agent using CrewAI
Primary responsibility: Automatically file ITR using mock APIs
"""

from crewai import Agent, Task, Crew, Process
from langchain_openai import ChatOpenAI
from utils.config import settings
from tools.itr_tools import (
    itr_login_tool,
    add_client_tool,
    get_prefill_data_tool,
    validate_itr_tool,
    save_draft_tool,
    set_verification_mode_tool,
    submit_itr_tool,
    get_acknowledgement_tool
)

# Initialize LLM
llm = ChatOpenAI(
    model="gpt-4o",
    api_key=settings.OPENAI_API_KEY
)


class ITRFilingCrew:
    """CrewAI setup for automated ITR filing"""
    
    def __init__(self):
        # ITR Filing Agent
        self.itr_agent = Agent(
            role='ITR Filing Specialist',
            goal='Automatically file Income Tax Returns using government APIs',
            backstory="""You are an expert CA specializing in ITR filing.
            You have deep knowledge of Indian tax laws and e-filing procedures.
            You can navigate the ITR portal, fetch prefill data, validate returns,
            and submit them successfully. You always follow the correct sequence
            of steps and handle errors gracefully.""",
            verbose=True,
            allow_delegation=False,
            llm=llm,
            tools=[
                itr_login_tool,
                add_client_tool,
                get_prefill_data_tool,
                validate_itr_tool,
                save_draft_tool,
                set_verification_mode_tool,
                submit_itr_tool,
                get_acknowledgement_tool
            ]
        )
        
        # Data Analyst Agent (for ITR data preparation)
        self.data_analyst = Agent(
            role='Tax Data Analyst',
            goal='Analyze financial data and prepare ITR forms',
            backstory="""You are a meticulous tax data analyst who can review
            financial documents, extract relevant information, and organize it
            according to ITR form requirements. You understand income heads,
            deductions, and how to optimize tax liability legally.""",
            verbose=True,
            allow_delegation=False,
            llm=llm
        )
        
        # Validator Agent
        self.validator = Agent(
            role='ITR Validator',
            goal='Ensure ITR data is accurate and complete before filing',
            backstory="""You are a quality control expert who reviews ITR data
            for accuracy, completeness, and compliance. You catch errors before
            submission and ensure all mandatory fields are filled correctly.""",
            verbose=True,
            allow_delegation=False,
            llm=llm
        )
    
    def file_itr_automatically(
        self,
        user_id: str,
        pan: str,
        assessment_year: str,
        itr_type: str = "ITR-1",
        include_prefill: bool = True
    ) -> str:
        """
        Automatically file ITR for a user
        
        Args:
            user_id: User ID
            pan: PAN number
            assessment_year: Assessment year (e.g., "2024-25")
            itr_type: ITR form type
            include_prefill: Whether to use government prefill data
        
        Returns:
            Filing result with acknowledgement number
        """
        
        # Task 1: Login and Authentication
        login_task = Task(
            description=f"""
            1. Login to ITR system using itr_login_tool
            2. Store the session ID for subsequent API calls
            3. Add the client (PAN: {pan}) for assessment year {assessment_year}
            4. Confirm successful client addition
            """,
            agent=self.itr_agent,
            expected_output="Session ID and Client Reference ID"
        )
        
        # Task 2: Fetch Prefill Data
        prefill_task = Task(
            description=f"""
            Using the session ID from the previous task:
            1. Fetch prefill data for PAN: {pan}, AY: {assessment_year}
            2. Extract salary information, TDS details, and deductions
            3. Summarize the key income and tax information
            """,
            agent=self.data_analyst,
            expected_output="Prefilled ITR data with income and tax details",
            context=[login_task]
        )
        
        # Task 3: Prepare and Validate ITR Data
        validation_task = Task(
            description=f"""
            Using the prefill data and session ID:
            1. Review the prefilled data for accuracy
            2. Ensure all mandatory fields are present
            3. Validate the ITR using validate_itr_tool
            4. If validation fails, identify and report errors
            5. If validation succeeds, proceed with the validation ID
            
            ITR Type: {itr_type}
            """,
            agent=self.validator,
            expected_output="Validation ID or list of errors",
            context=[login_task, prefill_task]
        )
        
        # Task 4: Save Draft and Set Verification Mode
        draft_task = Task(
            description="""
            Using the validation ID:
            1. Save the validated ITR as a draft using save_draft_tool
            2. Set the verification mode to 'eVerify Later'
            3. Confirm draft is ready for submission
            """,
            agent=self.itr_agent,
            expected_output="Draft ID and verification mode confirmation",
            context=[login_task, validation_task]
        )
        
        # Task 5: Submit ITR
        submission_task = Task(
            description="""
            Final submission:
            1. Submit the ITR using submit_itr_tool with the draft ID
            2. Capture the acknowledgement number
            3. Retrieve the acknowledgement using get_acknowledgement_tool
            4. Provide a complete summary of the filing
            """,
            agent=self.itr_agent,
            expected_output="Acknowledgement number and submission confirmation",
            context=[login_task, draft_task]
        )
        
        # Create and run the crew
        crew = Crew(
            agents=[self.itr_agent, self.data_analyst, self.validator],
            tasks=[login_task, prefill_task, validation_task, draft_task, submission_task],
            verbose=True,
            process=Process.sequential
        )
        
        result = crew.kickoff()
        
        return str(result)
    
    def get_itr_status(self, pan: str, assessment_year: str) -> str:
        """
        Check ITR filing status
        
        Args:
            pan: PAN number
            assessment_year: Assessment year
        
        Returns:
            Status information
        """
        
        status_task = Task(
            description=f"""
            1. Login to ITR system
            2. Add client for PAN: {pan}
            3. Fetch prefill data to check if ITR is already filed
            4. Report the current status
            """,
            agent=self.itr_agent,
            expected_output="ITR filing status"
        )
        
        crew = Crew(
            agents=[self.itr_agent],
            tasks=[status_task],
            verbose=True
        )
        
        result = crew.kickoff()
        return str(result)
    
    def get_prefill_summary(self, pan: str, assessment_year: str) -> str:
        """
        Get prefill data summary
        
        Args:
            pan: PAN number
            assessment_year: Assessment year
        
        Returns:
            Prefill data summary
        """
        
        prefill_task = Task(
            description=f"""
            1. Login to ITR system
            2. Add client for PAN: {pan}, AY: {assessment_year}
            3. Fetch and summarize prefill data
            4. Highlight key income sources and tax deductions
            """,
            agent=self.data_analyst,
            expected_output="Prefill data summary"
        )
        
        crew = Crew(
            agents=[self.itr_agent, self.data_analyst],
            tasks=[prefill_task],
            verbose=True
        )
        
        result = crew.kickoff()
        return str(result)
