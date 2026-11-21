from django.db.models import Count
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.filters import SearchFilter
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Document, QuestionHistory
from .serializers import (
    AskSerializer,
    DocumentListSerializer,
    DocumentSerializer,
    QuestionHistorySerializer,
)
from .services.errors import ServiceError
from .services.ingestion import reindex
from .services.qa_chain import answer_question


@extend_schema(
    parameters=[
        OpenApiParameter("search", str, description="جست‌وجو در عنوان و متن سند"),
        OpenApiParameter("is_indexed", bool, description="فیلتر بر اساس وضعیت ایندکس"),
    ]
)
class DocumentViewSet(viewsets.ModelViewSet):
    """Document CRUD. Create/update extract the text and index it automatically."""

    queryset = Document.objects.annotate(chunk_count=Count("chunks")).order_by("-updated_at")
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    filter_backends = [SearchFilter]
    search_fields = ["title", "content"]

    def get_serializer_class(self):
        return DocumentListSerializer if self.action == "list" else DocumentSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        flag = self.request.query_params.get("is_indexed")
        if flag is not None:
            qs = qs.filter(is_indexed=flag.lower() in ("1", "true", "yes"))
        return qs

    @extend_schema(request=None, responses=DocumentSerializer)
    @action(detail=True, methods=["post"])
    def reindex(self, request, pk=None):
        """Re-index one document (e.g. after an embedding failure)."""
        doc = self.get_object()
        reindex(doc)
        return Response(DocumentSerializer(self.get_queryset().get(pk=doc.pk)).data)


class AskView(APIView):
    @extend_schema(request=AskSerializer, responses={201: QuestionHistorySerializer})
    def post(self, request):
        """Ask a question: hybrid retrieval, grounded answer, saved to the history."""
        data = AskSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        try:
            result = answer_question(data.validated_data["question"], data.validated_data.get("top_k"))
        except ServiceError as exc:
            return Response({"detail": str(exc)}, status=exc.status_code)
        history = QuestionHistory.objects.create(question=data.validated_data["question"], **result)
        return Response(QuestionHistorySerializer(history).data, status=status.HTTP_201_CREATED)


class HistoryViewSet(viewsets.ReadOnlyModelViewSet):
    """Question/answer history, newest first."""

    queryset = QuestionHistory.objects.all()
    serializer_class = QuestionHistorySerializer
    filter_backends = [SearchFilter]
    search_fields = ["question", "answer"]
