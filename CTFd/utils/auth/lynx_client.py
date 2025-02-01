import os
import grpc
from google.protobuf import struct_pb2
from dotenv import load_dotenv
from CTFd.utils.logging import log
from CTFd.utils import get_app_config
import sys
from pathlib import Path

# Add the current directory to Python path
sys.path.append(str(Path(__file__).parent))

# Import pre-generated proto files
import lynx_auth_pb2
import lynx_auth_pb2_grpc

load_dotenv()

class LynxAuthClient:
    def __init__(self):
        self.channel = grpc.secure_channel(
            get_app_config('LCA_URI') or os.getenv('LCA_URI'),
            grpc.ssl_channel_credentials()
        )
        self.stub = lynx_auth_pb2_grpc.AuthenticationStub(self.channel)
        
    def generate_otp(self, roll_no):
        try:
            request = lynx_auth_pb2.GenerateOTPRequest(
                clientID=os.getenv('GRPC_CLIENT_ID'),
                clientSecret=os.getenv('GRPC_CLIENT_SECRET'),
                rollNo=roll_no
            )
            response = self.stub.GenerateOTP(request)
            return True, response.message
        except grpc.RpcError as e:
            log("auth", f"OTP Generation failed for {roll_no}: {e.details()}")
            return False, e.details()

    def verify_otp(self, roll_no, otp):
        try:
            request = lynx_auth_pb2.VerifyOTPRequest(
                clientID=os.getenv('GRPC_CLIENT_ID'),
                clientSecret=os.getenv('GRPC_CLIENT_SECRET'),
                rollNo=roll_no,
                otp=otp
            )
            response = self.stub.VerifyOTP(request)
            return True, response.message, response.Details
        except grpc.RpcError as e:
            log("auth", f"OTP Verification failed for {roll_no}: {e.details()}")
            return False, e.details(), None