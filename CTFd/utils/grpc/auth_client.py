import grpc
from . import authentication_pb2
from . import authentication_pb2_grpc
import logging
import os
import time

class AuthenticationClient:
    def __init__(self, 
                 host=os.getenv('GRPC_AUTH_HOST', 'localhost'), 
                 port=int(os.getenv('GRPC_AUTH_PORT', '50051')), 
                 use_ssl=False,
                 max_retries=3):
        self.host = host
        self.port = port
        self.use_ssl = use_ssl
        self.channel = None
        self.stub = None
        self.max_retries = max_retries
        self._connect_with_retry()

    def _connect_with_retry(self):
        """Try to connect with retries"""
        retries = 0
        while retries < self.max_retries:
            try:
                self._connect()
                return  # Connection successful
            except Exception as e:
                retries += 1
                logging.warning(f"Connection attempt {retries}/{self.max_retries} failed: {e}")
                if retries >= self.max_retries:
                    logging.error(f"Failed to connect after {self.max_retries} attempts")
                    # Don't raise, allow lazy connection in methods
                    return
                time.sleep(2)  # Wait before retrying

    def _connect(self):
        """Establish connection to gRPC server"""
        try:
            if self.use_ssl:
                # For secure connection (HTTPS)
                credentials = grpc.ssl_channel_credentials()
                self.channel = grpc.secure_channel(
                    f'{self.host}:{self.port}', 
                    credentials
                )
            else:
                # For non-secure connection (HTTP)
                self.channel = grpc.insecure_channel(f'{self.host}:{self.port}')
            
            self.stub = authentication_pb2_grpc.AuthenticationStub(self.channel)
            # Test connection with shorter timeout
            grpc.channel_ready_future(self.channel).result(timeout=3)
            logging.info(f"Successfully connected to gRPC server at {self.host}:{self.port}")
        except Exception as e:
            logging.error(f"Failed to connect to gRPC server at {self.host}:{self.port}: {e}")
            self.channel = None
            self.stub = None
            raise

    def generate_otp(self, client_id: str, client_secret: str, roll_no: int):
        try:
            if not self.stub:
                self._connect()
            
            # Ensure client_id and client_secret are properly formatted strings
            client_id = str(client_id).strip()
            client_secret = str(client_secret).strip()
            
            # Debug logging
            logging.info(f"Attempting OTP generation for roll_no: {roll_no}")
            logging.debug(f"Client ID length: {len(client_id)}")
            logging.debug(f"Client Secret length: {len(client_secret)}")
            
            request = authentication_pb2.GenerateOTPRequest(
                clientID=client_id,
                clientSecret=client_secret,
                rollNo=roll_no
            )
            
            response = self.stub.GenerateOTP(request)
            return True, response.message
        except grpc.RpcError as e:
            if e.code() == grpc.StatusCode.PERMISSION_DENIED:
                logging.error(f"Authentication failed - Invalid credentials")
                return False, "Invalid Client ID or Client Secret. Please check your configuration."
            logging.error(f"gRPC error in generate_otp: {e}")
            return False, f"gRPC error: {str(e)}"
        except Exception as e:
            logging.error(f"Unexpected error in generate_otp: {e}")
            return False, f"Unexpected error: {str(e)}"

    def verify_otp(self, client_id: str, client_secret: str, roll_no: int, otp: int):
        try:
            if not self.stub:
                self._connect()

            request = authentication_pb2.VerifyOTPRequest(
                clientID=client_id,
                clientSecret=client_secret,
                rollNo=roll_no,
                otp=otp
            )
            response = self.stub.VerifyOTP(request)

            # Extract studentName from the response
            student_name = response.Details.fields["studentName"].string_value

            return True, response.message, student_name
        except grpc.RpcError as e:
            logging.error(f"gRPC error in verify_otp: {e}")
            return False, f"gRPC error: {str(e)}", None
        except Exception as e:
            logging.error(f"Unexpected error in verify_otp: {e}")
            return False, f"Unexpected error: {str(e)}", None

    def close(self):
        self.channel.close()